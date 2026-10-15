---
doc: spec
status: draft
---

# Voice of Experience (صوت الخبرة) — Technical Specification

A voice-first knowledge preservation web application for oil and gas data engineers that captures spoken troubleshooting expertise in Libyan Arabic and English, transcribes audio through a quota-resilient multi-tier STT pipeline, extracts structured diagnostic cards grounded in verbatim transcript quotes with verification, and provides search with a strict "I don't know" boundary.

---

## How This Works, In Plain Language

The system consists of three lightweight parts running locally on your laptop:
1. **The Browser Interface (Frontend):** A clean web page built with HTML, modern CSS, and JavaScript. It lets engineers search existing troubleshooting advice, record short voice notes through the laptop microphone (or upload a pre-recorded audio file), and edit speech-to-text transcripts in a plain RTL textarea with a count of `[unclear]` words highlighted for attention.
2. **The Local Application Server (Python / FastAPI):** A local service that handles audio uploads, converts recordings to OGG via ffmpeg, communicates with external AI services securely using keys from `.env`, runs extraction routines with quote verification, and performs search ranking.
3. **The Local Storage (SQLite & Audio Files):** A local SQLite database that stores structured expert cards, transcript cache, and search indexes, accompanied by a local `audio/` folder holding original recordings (private, gitignored).

### Why This Shape
Rather than relying on heavy cloud infrastructure, authentication servers, or external vector databases, this architecture is completely local and reproducible. Every sensitive recording stays on your machine unless explicitly sent to AI endpoints for transcription, API keys never touch the browser, and cards are persisted locally without cloud database lock-in.

---

## The Core Journey Through the System

Implements `prd.md > 1. The Core Journey`.

```mermaid
sequenceDiagram
    autonumber
    actor Expert as Expert Engineer
    participant UI as Browser (SPA)
    participant Server as FastAPI Backend
    participant Cache as Local SQLite & Audio Cache
    participant STT as Multi-Tier STT (Gemini / Groq)
    participant Extractor as AI Extractor (separate model)

    Note over Expert, UI: 1. Setup & Capture
    Expert->>UI: Enters name, selects Real/Demo tag, consents
    Expert->>UI: Records audio (mic) or uploads audio file
    UI->>Server: POST /api/transcribe (audio blob or file)

    Note over Server, Cache: 2. Convert & Transcribe
    Server->>Server: ffmpeg converts WebM/WAV → OGG
    Server->>Cache: Compute SHA-256 hash & check transcript cache
    alt Cache Hit
        Cache-->>Server: Return cached transcript
    else Cache Miss
        Server->>STT: Attempt 1: Primary Gemini model (with retry/backoff)
        opt On 503 / 429 Quota Exceeded
            Server->>STT: Attempt 2: Secondary Gemini model
        end
        opt On Secondary Failure
            Server->>STT: Attempt 3: Groq whisper-large-v3 (fallback)
        end
        STT-->>Server: Raw transcript + service provenance
        Server->>Cache: Save transcript to cache
    end
    Server-->>UI: Return transcript, fallback notice, and [unclear] tags

    Note over Expert, UI: 3. Review & Structuring
    UI->>Expert: Display transcript in RTL textarea; count [unclear] words
    Expert->>UI: Fixes dialect phrases; clicks "Extract card"
    UI->>Server: POST /api/extract (edited transcript)
    Server->>Extractor: Extract JSON: each field = verbatim_quote + optional summary
    Extractor-->>Server: JSON {field, verbatim_quote, summary}
    Server->>Server: Normalize & verify each quote is a substring of transcript
    Note over Server: If quote not found → "Could not be verified – please edit"
    Note over Server: If model says nothing stated → "Not mentioned"
    Server-->>UI: Structured card preview (quotes shown as primary display values)

    Note over Expert, Cache: 4. Approval & Persistence
    Expert->>UI: Marks "Expert-Approved" and clicks Save
    UI->>Server: POST /api/cards (approved card + metadata)
    Server->>Cache: Save card to SQLite + save audio file to disk
    Server-->>UI: Card created successfully
    UI->>UI: Card appears at top of library with [Real]/[Demo] badge
```

---

## Stack

- **Backend Framework:** **Python 3.10+ with FastAPI** (`v0.115+`) and **Uvicorn**.
  *Rationale:* Native fit for the learner's Python and data processing background; provides rapid async endpoints, typed Pydantic validation, and minimal boilerplate.
  *Doc link:* [FastAPI Documentation](https://fastapi.tiangolo.com/)
- **Frontend Architecture:** **Vanilla HTML5, CSS3, and JavaScript (ES6 Modules)**.
  *Rationale:* No heavy bundlers or build-step dependencies to debug. Direct DOM manipulation, MediaRecorder API for audio capture, and CSS variables for the industrial design system.
  *Doc link:* [MDN Web Docs — MediaStream Recording API](https://developer.mozilla.org/en-US/docs/Web/API/MediaStream_Recording_API)
- **Audio Conversion:** **ffmpeg** (provided directly via `imageio-ffmpeg` Python dependency, no external system install or symlink required).
  *Rationale:* Browser `MediaRecorder` typically outputs WebM/Opus. Gemini multimodal accepts OGG/WAV best. ffmpeg converts WebM → OGG before API calls. Also supports uploaded audio in various formats.
  *Doc link:* [imageio-ffmpeg Documentation](https://github.com/imageio/imageio-ffmpeg)
- **Local Database & Cache:** **SQLite3** via standard library `sqlite3` + local filesystem for audio assets.
  *Rationale:* Zero configuration, file-based persistence, instant search queries, and built-in transactional safety without running a separate database server.
  *Doc link:* [Python sqlite3 Documentation](https://docs.python.org/3/library/sqlite3.html)
- **Primary Speech-to-Text:** Configurable via `STT_PRIMARY_MODEL` in `.env` (default: `gemini-3.8-flash`).
  *Rationale:* Proven in Day-1 gate testing to transcribe Libyan Arabic code-switching and preserve technical terms (`accuracy`, `data leakage`, `stratified split`, `normalization`) in Latin script.
  *Doc link:* [Google AI Studio API Docs](https://ai.google.dev/api)
- **Secondary Speech-to-Text:** Configurable via `STT_SECONDARY_MODEL` in `.env` (default: `gemini-3.5-flash`).
  *Rationale:* First automatic failover if the primary model encounters transient 503 capacity spikes or free-tier daily caps.
- **Tertiary Fallback Speech-to-Text:** **Groq Cloud Whisper Large v3** (`whisper-large-v3` via Groq REST API).
  *Rationale:* Ultra-fast (sub-2s) fallback that guarantees transcription when both Gemini models are unavailable.
  *Doc link:* [Groq Audio API Reference](https://console.groq.com/docs/speech-text)
- **Card Extraction Model:** Configurable via `EXTRACTION_MODEL` in `.env` (default: `gemini-3.1-flash-lite`).
  *Rationale:* A different model from the STT models so extraction requests do not deplete the ~20 requests/day STT quota.
- **Search & Anti-Hallucination Matching:** **Character n-gram (3–5) TF-IDF** on Arabic-normalized text + small alias table, implemented in Python with `scikit-learn`.
  *Rationale:* Deterministic, zero-cost, runs completely offline, handles Arabic morphological variation through character n-grams, and allows exact threshold calibration against the PRD's 10-query tuning set and 6-query held-out test set. Embedding-based search kept as a fallback option only if held-out test results are poor.
  *Doc link:* [scikit-learn TfidfVectorizer](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html)

---

## Where It Runs and How Someone Tries It

- **Runtime Environment:** Linux / WSL2 (Ubuntu), Python 3.10+ (ffmpeg binary bundled directly via `imageio-ffmpeg`).
- **Target Browser:** Desktop Chrome (per `prd.md > 3. Look and Feel`).
- **Configuration:** Secrets and configurable model names stored exclusively in `.env` in the workspace root:
  ```bash
  GEMINI_API_KEY=your_google_ai_studio_key
  GROQ_API_KEY=your_groq_api_key

  # Optional: override default model names
  STT_PRIMARY_MODEL=gemini-3.8-flash
  STT_SECONDARY_MODEL=gemini-3.5-flash
  EXTRACTION_MODEL=gemini-3.1-flash-lite
  ```
- **Execution Command:**
  ```bash
  # 1. Install Python dependencies (includes imageio-ffmpeg for standalone ffmpeg binary)
  pip install -r requirements.txt

  # 2. Run the application
  python3 -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload
  ```
- **Demo Verification URL:** Open `http://127.0.0.1:8000` in desktop Chrome.
- **Seed Card Generation:**
  ```bash
  # Runs each audio file in samples/ through the app's own API pipeline
  python3 scripts/seed_cards.py
  ```
- **Packaging for Submission (`6-ship`):** The repository includes consented audio clips in `samples/` (public, committed). All other recordings stay in `audio/` (private, gitignored). Deployment is optional; the local application is fully demonstrable for the Devpost video recording.

---

## Look and Feel

Implements `prd.md > 3. Look and Feel` and `scope.md > Inspiration & Identity`.

- **Visual Tone:** Industrial, safety-conscious, calm, high-contrast engineering tool.
- **Palette Tokens:**
  - Background: Warm light gray (`#F4F4F6` / `#F8F9FA`)
  - Primary text: Deep dark navy (`#0F172A`)
  - Interactive brand: Deep Teal (`#0F766E`)
  - Caution highlight: Reserved Amber (`#B45309`) — strictly reserved for human-stated cautions
  - Real Origin Badge: Forest Green badge with clear text `[Real]`
  - Demo Origin Badge: Slate Gray badge with clear text `[Demo]`
  - Fallback STT Notice: Muted Blue banner informing the user if Groq fallback was triggered
  - Unclear Token Highlight: Pale Amber background (`#FEF3C7`) with dashed underline (`#D97706`) in the `[unclear]` counter display
  - Unverified Field Notice: Light Rose background with text *"Could not be verified – please edit"*
- **Typography:**
  - English structure and UI: **IBM Plex Sans**
  - Arabic dialect and search inputs: **IBM Plex Sans Arabic**
- **Directionality:** Bidirectional. English shell is LTR; search inputs, transcript editor, and card diagnostic bodies are RTL.
- **Accessibility:** WCAG AA (minimum 4.5:1 contrast against warm gray backgrounds).

---

## Components

### 1. Main Surface & Search Interface
- **Role:** Displays the safety banner, search bar with hint chips, search results counter, and the card library.
- **Connects to:** `GET /api/cards`, `GET /api/search?q=...`.
- **Implements:** `prd.md > 2.1 Main Surface` & `prd.md > 4.2 Search & "I Don't Know" Anti-Hallucination Fallback`.
- **Behaviors:**
  - Typing a symptom query triggers server-side character n-gram TF-IDF similarity ranking across card text fields and transcripts (after Arabic normalization and alias expansion).
  - If top score ≥ τ (calibrated relevance threshold): displays ranked cards with a `"Best match"` badge on the top card.
  - If top score < τ: renders the calm *"I don't know — no matching card found"* anti-hallucination panel with options to browse all or record an expert note.

### 2. Contribution Flow (Single-Page Sequential Sections)
- **Role:** Guides the expert contributor through setup, recording/upload, transcript review, and card approval on a single scrollable page with sequential sections that unlock progressively.
- **Connects to:** `POST /api/transcribe`, `POST /api/extract`, `POST /api/cards`.
- **Implements:** `prd.md > 2.2 Contribution Modal` & `prd.md > 4.3 Contribution Wizard`.
- **Sections:**
  - **Section 1 (Setup):** Expert name input, Real vs. Demo origin selector, confidentiality notice (*"Do not mention company system names, IP addresses, or passwords"*), and AI processing consent checkbox. "Continue" is disabled until all are filled.
  - **Section 2 (Capture):** Two options side-by-side:
    - **Record:** Record/Stop button with elapsed time counter; auto-stops at 2:00 minutes; inline playback preview. No live sound-level visualizer (simplified).
    - **Upload:** File picker accepting `.ogg`, `.webm`, `.wav`, `.mp3` audio files.
    - **Upload Limits:** Enforces a maximum file size of **10 MB** and maximum duration of **2 minutes (120s)**. Rejects files exceeding these limits with clear HTTP 400 validation messages.
    - Both paths send audio to `POST /api/transcribe`. The server securely saves uploaded bytes with a generated temporary name (never using the user-provided filename as a filesystem path), calculates the SHA-256 hash on the **original** incoming bytes, and converts to OGG via ffmpeg before STT.
  - **Section 3 (Transcript Review & Edit):** Audio player above a plain RTL `<textarea>` containing the raw transcript. A counter above the textarea shows *"N [unclear] words remaining"* with the count highlighted in Pale Amber when > 0. The expert edits freely. Displays a badge indicating transcription provenance (e.g. *"Transcribed by gemini-3.5-flash"* or *"⚠ Transcribed via Groq fallback"*). Button: *"Extract card"*.
  - **Section 4 (Review & Approve):** Displays the 5 extracted diagnostic fields. Each field's **primary display value is the verbatim quote** from the transcript (shown in a styled blockquote), with an optional AI-generated summary shown below in smaller text. Fields where the AI model indicated nothing was stated show *"Not mentioned"*. Fields where quote verification failed show *"Could not be verified – please edit"* in a highlighted notice. Checkbox to mark **Expert-Approved**; Save button.

### 3. Audio Conversion Layer (ffmpeg)
- **Role:** Safely normalizes incoming audio from any browser-recorded or uploaded format to OGG/Opus before sending to STT APIs.
- **Implements:** User requirement (4) & upload security/integrity fixes.
- **Behavior & Security Constraints:**
  - **Never use uploaded filename as path:** The uploaded file is saved using a cryptographically random filename (e.g. `uuid4().hex` in a secure temp directory) to prevent path traversal or shell injection.
  - **SHA-256 on Original Bytes:** Computes the SHA-256 hash directly on the **ORIGINAL uploaded bytes**, *not* on the re-encoded OGG. (Ogg muxing adds a random stream serial number on each encoding run, which causes re-encoded file bytes to differ every run). This original-bytes hash is used as the key for `stt_cache` and for seed idempotency.
  - **Safe Subprocess Execution:** Invokes ffmpeg via `subprocess.run([...])` using an **explicit argument list** (never `shell=True` and never shell string formatting):
    ```python
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), "-c:a", "libopus", "-ar", "48000", "-ac", "1", str(output_path)],
        check=True,
        capture_output=True
    )
    ```
  - **Upload Limits:** Max 10 MB file size limit and max 2 minutes (120 seconds) audio duration check (via `ffprobe` or duration probing).
  - If ffmpeg binary is not found, the endpoint returns a clear error: *"ffmpeg binary not found. Please ensure imageio-ffmpeg is installed in requirements.txt"*.

### 4. Resilient STT Transcription Pipeline (Backend)
- **Role:** Coordinates multi-tier speech-to-text with automatic backoff, caching, and fallback.
- **Connects to:** Local cache, Google Gemini REST API, Groq REST API.
- **Implements:** `scope.md > Key Risk to Test First` & Day-1 Gate decisions.
- **Model Configuration:** Model names are read from `.env` at startup (keys: `STT_PRIMARY_MODEL`, `STT_SECONDARY_MODEL`, `EXTRACTION_MODEL`, `EXTRACTION_FALLBACK_MODEL`) with defaults. This allows swapping models without code changes as Google or Groq retires/adds model versions.
- **Architecture & Failover Logic:**
  1. **SHA-256 Audio Cache Check:** Computes the SHA-256 hash of the **original uploaded audio bytes**. If a cached transcript exists in the `stt_cache` table, returns immediately with 0 API calls.
  2. **Primary Tier (configured model, default `gemini-3.8-flash`):** Calls Gemini multimodal audio endpoint with verbatim prompt. On HTTP 503 or 429, executes exactly 1 retry with a ~3s backoff before failing over to the secondary tier to keep worst-case wait minimal.
  3. **Secondary Tier (configured model, default `gemini-3.5-flash`):** If primary exhausts its retry, attempts the secondary model with the same fast failover logic.
  4. **Tertiary Fallback Tier (`Groq whisper-large-v3`):** If both Gemini models fail (or hit quota), falls back to Groq Whisper Large v3 (`temperature=0`, `language="ar"`, with domain glossary prompt).
  5. **Provenance Tagging:** Attaches metadata (`stt_provider: "gemini-3.8-flash"` or `stt_provider: "groq-fallback"`) so the UI displays an informative notice when fallback occurred.
- **Domain Glossary Prompt (Gemini):**
  ```text
  Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, keep English terms in Latin letters.
  Transcribe exactly what was said. Do not correct, rephrase, or fix wording. Do not include timestamps. If a word is unclear, write [unclear] instead of guessing.
  Domain glossary for spelling guidance: telemetry, pipeline, drift, schema, timestamp, batch, missing value, NaN, outlier, sensor, distribution, latency, partition, query, memory leak, index, join, target leakage, stratified split, normalization, train, test, overfit, scikit-learn, accuracy, preprocessing, cross-validation, feature engineering, confusion matrix, regression, classification, sampling, annotation, calibration, deployment, inference.
  ```
- **Groq Fallback Prompt:**
  ```text
  Libyan Arabic dialect mixed with English technical terms, transcribe verbatim, keep English terms in Latin letters.
  ```
  (Whisper uses this as `prompt` parameter, with `language="ar"`, `temperature=0`.)

### 5. Quote-Verified AI Card Extraction Engine
- **Role:** Extracts structured diagnostic fields from the expert-edited transcript with anti-hallucination verification based on verbatim quotes.
- **Connects to:** Configured primary extraction model (`EXTRACTION_MODEL`, default: `gemini-3.1-flash-lite`), secondary fallback model (`EXTRACTION_FALLBACK_MODEL`, default: `gemini-3.6-flash`), tertiary fallback model (Groq `llama-3.3-70b-versatile`), and SQLite extraction cache.
- **Implements:** `prd.md > 4.3 (Step 4)` & user constraints on quote verification.
- **Extraction Caching:**
  - Before calling any extraction LLM, computes the SHA-256 hash of the edited transcript text.
  - If a record exists in `extraction_cache`, the parsed JSON is returned immediately with 0 LLM calls.
- **Extraction Protocol:**
  - Instructs the LLM to output strict JSON containing the 5 fields, where **every** field includes both a verbatim quote copied exactly from the transcript and an optional summary:
    ```json
    {
      "problem_summary": {
        "verbatim_quote": "exact words from transcript...",
        "summary": "optional short summary"
      },
      "possible_causes": {
        "verbatim_quote": "exact words from transcript...",
        "summary": "optional short summary"
      },
      "checks": {
        "verbatim_quote": "exact words from transcript...",
        "summary": "optional short summary"
      },
      "solution_steps": {
        "verbatim_quote": "exact words from transcript...",
        "summary": "optional short summary"
      },
      "cautions": {
        "verbatim_quote": "exact words from transcript or null if not stated",
        "summary": "optional short summary or null",
        "stated": true
      }
    }
    ```
  - The extraction prompt instructs the model: *"If the expert did not mention anything for a field, set `verbatim_quote` to null and `stated` to false. Do not invent content."*
- **Quote Verification — Arabic-Aware Normalization & Integrity Rules:**
  The backend verifies each `verbatim_quote` by checking whether its **normalized** form appears as a substring of the **normalized** transcript. Normalization steps:
  1. **Strip Arabic diacritics (tashkeel):** Remove characters in Unicode range `\u0610`–`\u061A`, `\u064B`–`\u065F`, `\u0670`.
  2. **Unify Alef variants:** Map `إ`, `أ`, `آ`, `ٱ` → `ا`.
  3. **Unify Ya:** Map `ي` ↔ `ى` to a single form (`ي`).
  4. **Unify Ta Marbuta / Ha:** Map `ة` → `ه`.
  5. **Lowercase Latin letters:** Convert all Latin characters (`a-z`, `A-Z`) to lowercase (e.g. `Accuracy` → `accuracy`).
  6. **Strip punctuation:** Remove all Unicode punctuation categories.
  7. **Collapse whitespace:** Replace runs of whitespace with a single space; strip leading/trailing.
- **Verification Integrity Constraints (Rejection Rules):**
  - **Substring match:** The normalized quote must exist as a contiguous substring of the normalized transcript.
  - **Length cap (60% rule):** Reject any quote whose character length exceeds 60% of the full transcript length (`len(norm_quote) > 0.6 * len(norm_transcript)`). A field quoting the whole speech is not a targeted excerpt.
  - **Distinct quotes rule:** Reject identical quotes used for two different fields. Each extracted field must cite a distinct portion of the transcript; if two fields share the exact same quote, they are rejected.
- **Verification Outcomes:**
  - **Quote valid (passes substring, length cap, and distinctness):** Field is accepted. The card displays the verbatim quote as its primary value.
  - **Quote verification fails (not found, > 60% length, or duplicate quote across fields):** Field value is set to `"Could not be verified – please edit"` — shown in a highlighted notice in the UI so the expert can manually fix it.
  - **Model says field was not stated (`stated: false` or `verbatim_quote: null`):** Field value is set to `"Not mentioned"` with neutral styling (no amber, no alarm).
  - For the `cautions` field specifically: if not mentioned, PRD requires displaying *"No caution stated by the expert"* in neutral styling.

### 6. Card Library & Audio Persistence Store
- **Role:** Stores seed cards and user-contributed cards in SQLite, serves audio files, and loads seed cards on fresh initialization.
- **Connects to:** `data/voice_experience.db`, `audio/` directory (private), `samples/` directory (public consented clips).
- **Implements:** `prd.md > 4.1 Cards Library & Display`.
- **Card Display:** Each card shows its fields with the **verbatim quote as the primary display value** (shown in a styled blockquote), and the optional AI summary shown smaller beneath it. This ensures the expert's own words are always front and center.

### 7. Character N-Gram Search Engine
- **Role:** Provides Arabic-aware search over card content with a calibrated anti-hallucination "I don't know" threshold.
- **Connects to:** SQLite card data.
- **Implements:** `prd.md > 4.2 Search & "I Don't Know" Anti-Hallucination Fallback`.
- **Algorithm:**
  1. **Text Preparation:** For each card, concatenate `problem_summary`, `possible_causes`, `checks`, `solution_steps`, `cautions`, and `transcript` into a single searchable document. Apply the same Arabic normalization defined in Component 5.
  2. **Alias Expansion:** Before vectorizing, expand a small alias table to bridge dialect transliterations and standard English technical terms:
     | Arabic Transliteration Alias | English Equivalent |
     |---|---|
     | التست | test |
     | الترين | train |
     | الموديل | model |
     | نورميزايليشن | normalization |
     | داتا ليكيج | data leakage |
     | أكيسيري | accuracy |
     | ماسينج فاليو | missing value |
     | بروسيسينج | processing |
     *(Note: The alias table comes from observed Whisper transliterations during audio tests. Crucially, the 16 evaluation queries defined in PRD Section 4.2 must NOT rely on the alias table to pass; they evaluate intrinsic character n-gram retrieval performance).*
  3. **TF-IDF Vectorization:** `TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))` from scikit-learn is **fitted on the card documents only**. The query is never included in the fit; it is vectorized via `vectorizer.transform([query])`.
  4. **Scoring:** Cosine similarity between query vector and each card vector. Rank descending.
  5. **Threshold Calibration:** The similarity threshold τ is calibrated on the PRD's 10-query tuning set (5 in-scope must pass, 5 out-of-scope must fail). Results are then checked on the 6-query held-out test set (none of which rely on the alias table).
  6. **Embedding Fallback (Conditional):** If the held-out test results show poor discrimination (e.g., false positives or false negatives), an embedding-based approach using a free embedding API can be added as an alternative scorer. This is not the default path.

---

## Data Model

### SQLite Schema

```sql
-- Diagnostic Cards Table
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    expert_name TEXT NOT NULL,
    origin_tag TEXT CHECK(origin_tag IN ('Real', 'Demo')) NOT NULL,
    problem_summary_quote TEXT NOT NULL,
    problem_summary TEXT,
    possible_causes_quote TEXT NOT NULL,
    possible_causes TEXT,
    checks_quote TEXT NOT NULL,
    checks TEXT,
    solution_steps_quote TEXT NOT NULL,
    solution_steps TEXT,
    cautions_quote TEXT,
    cautions TEXT,
    has_caution BOOLEAN NOT NULL,
    transcript TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    audio_duration REAL NOT NULL,
    stt_provider TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by_expert BOOLEAN NOT NULL
);

-- Transcription Cache Table
CREATE TABLE IF NOT EXISTS stt_cache (
    audio_hash TEXT PRIMARY KEY,   -- SHA-256 of ORIGINAL uploaded audio bytes (avoids re-encoding serial jitter)
    raw_transcript TEXT NOT NULL,
    stt_provider TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Extraction Cache Table
CREATE TABLE IF NOT EXISTS extraction_cache (
    transcript_hash TEXT PRIMARY KEY, -- SHA-256 of edited transcript
    extracted_json TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key design notes:**
- Each card field has a `_quote` column (the verbatim transcript excerpt, displayed as primary value) and an optional summary column (secondary).
- `approved_by_expert` has **no default** — it must be explicitly set by the save endpoint.
- `has_caution` has **no default** — it reflects whether the model found a caution in the transcript.

### Example Card (JSON Representation)

Based on audio `04_data_leakage.ogg` (origin: **Demo** — read by a different person from a prepared script):

```json
{
  "id": "card_04_data_leakage",
  "expert_name": "Demo Speaker",
  "origin_tag": "Demo",
  "problem_summary_quote": "الموديل يعطي accuracy عالية بشكل مريب في test وبعدين في الواقع يطيح",
  "problem_summary": "Data leakage causing misleadingly high test accuracy",
  "possible_causes_quote": "المعلومات من test دخلت في التدريب من غير ما نقصدوا مثلاً لما نعملوا normalization على كل البيانات قبل ما نقسموا test وtrain أو لما نفس الحالة تتكرر في الجهتين",
  "possible_causes": "Information from test set entered training unintentionally",
  "checks_quote": "نشوف هل في صفوف مكررة بين المجموعتين ونشوفوا هل النتيجة عالية بزاف على غير العادة",
  "checks": "Check for duplicate rows and suspiciously high results",
  "solution_steps_quote": "نقسموا البيانات أول شيء وبعدين نعملوا processing على train فقط",
  "solution_steps": "Split data first, then process only the training set",
  "cautions_quote": "إذا النتيجة تبان مثالية شك فيها أول",
  "cautions": "If results look perfect, suspect them first",
  "has_caution": true,
  "transcript": "تسرب البيانات، المشكلة اللي شفتها مرات الموديل يعطي accuracy عالية بشكل مريب في test، وبعدين في الواقع يطيح. السبب غالباً data leakage، يعني المعلومات من test دخلت في التدريب من غير ما نقصدوا. مثلاً لما نعملوا normalization على كل البيانات قبل ما نقسموا test وtrain، أو لما نفس الحالة تتكرر في الجهتين. باش نتأكد، نشوف هل في صفوف مكررة بين المجموعتين، ونشوفوا هل النتيجة عالية بزاف على غير العادة. الحل نقسموا البيانات أول شيء، وبعدين نعملوا processing على train فقط. وتحذير: إذا النتيجة تبان مثالية، شك فيها أول.",
  "audio_path": "audio/04_data_leakage.ogg",
  "audio_duration": 48.5,
  "stt_provider": "gemini-3.5-flash",
  "approved_by_expert": true
}
```

---

## File Structure

```
/home/sara/Desktop/Project/
├── server/
│   ├── __init__.py
│   ├── main.py              # FastAPI app init, routes, static mount, config loading
│   ├── config.py            # Reads .env: model names, API keys, paths
│   ├── stt_pipeline.py      # Resilient STT: Primary → Secondary → Groq + cache
│   ├── audio_convert.py     # ffmpeg WebM/WAV → OGG conversion wrapper
│   ├── extractor.py         # AI structuring + verbatim quote verification engine
│   ├── normalizer.py        # Arabic normalization: diacritics, alef/ya/ta-marbuta, whitespace
│   ├── search_engine.py     # Character n-gram TF-IDF + alias table + threshold
│   └── database.py          # SQLite connection, schema migrations, and queries
├── scripts/
│   └── seed_cards.py        # Reads private audio/ by default; copies to samples/ only after written consent exists; sends through real pipeline
├── static/
│   ├── index.html           # Main SPA: search, library, and contribution flow
│   ├── css/
│   │   └── main.css         # Design system tokens, layout, typography, RTL support
│   └── js/
│       ├── app.js           # Search, library rendering, card toggle, audio playback
│       ├── contribution.js  # Sequential section flow, validation, submission
│       └── recorder.js      # MediaRecorder wrapper, upload handler
├── audio/                   # Private audio storage (gitignored) — all recordings land here
├── samples/                 # Public consented audio clips only (committed to repo)
│   ├── 04_data_leakage.ogg
│   └── 06_nan_missing_class.ogg
├── data/                    # SQLite database file (gitignored)
│   └── voice_experience.db
├── devpost/                 # Hackathon planning workspace
│   ├── learner-profile.md
│   ├── scope.md
│   ├── prd.md
│   └── spec.md              # This technical specification
├── .env                     # API keys + model config (gitignored)
├── .gitignore               # Ignores .env, audio/, data/, __pycache__/, node_modules/
├── requirements.txt         # fastapi, uvicorn, requests, python-dotenv, python-multipart, pydantic, scikit-learn, imageio-ffmpeg
├── requirements-dev.txt     # httpx, pytest
└── README.md
```

---

## External Services and Dependencies

1. **Google Gemini API (Google AI Studio)**
   - **Endpoints (model name is configurable):**
     - STT Primary: `POST https://generativelanguage.googleapis.com/v1beta/models/{STT_PRIMARY_MODEL}:generateContent`
     - STT Secondary: `POST https://generativelanguage.googleapis.com/v1beta/models/{STT_SECONDARY_MODEL}:generateContent`
     - Extraction Primary: `POST https://generativelanguage.googleapis.com/v1beta/models/{EXTRACTION_MODEL}:generateContent`
     - Extraction Fallback: `POST https://generativelanguage.googleapis.com/v1beta/models/{EXTRACTION_FALLBACK_MODEL}:generateContent` (model name verified at build time from provider model list)
   - **Auth:** Header `x-goog-api-key: $GEMINI_API_KEY` (never in URL).
   - **Free-Tier Limits:** ~20 requests per day per model; transient 503 capacity spikes during peak load.
   - **Handling:** Retry with exponential backoff, SHA-256 transcript cache, separate extraction model and fallback.
2. **Groq Cloud Audio API**
   - **Endpoint:** `POST https://api.groq.com/openai/v1/audio/transcriptions`
   - **Model:** `whisper-large-v3`
   - **Auth:** Header `Authorization: Bearer $GROQ_API_KEY`
   - **Free-Tier Limits:** Generous rate limits (requests per minute), highly resilient fallback.
   - **Cost:** Free tier ($0.00).
3. **ffmpeg (Bundled via imageio-ffmpeg)**
   - **Purpose:** Audio format conversion (WebM/WAV/MP3 → OGG/Opus).
   - **Install:** Bundled directly via `requirements.txt` (`imageio-ffmpeg`). No external system package or symlink required.
   - **Doc link:** [imageio-ffmpeg Documentation](https://github.com/imageio/imageio-ffmpeg)

---

## Seed Card Generation

Implements `scope.md > POC Boundary` requirement that seed cards are created through the application's own contribution pipeline.

**`scripts/seed_cards.py`** is a Python script that:
1. Reads audio files from private `audio/` by default (e.g. `04_data_leakage.ogg`, `06_nan_missing_class.ogg`).
2. Only copies a file from `audio/` to public `samples/` when written consent explicitly exists for that clip.
3. For each clip, computes the SHA-256 of the **original audio bytes** and checks for an existing card or transcript in the cache for idempotency.
4. Sends a `POST /api/transcribe` request to the running local server — exercising the real STT pipeline (Gemini → Groq fallback, ffmpeg conversion, caching).
5. Sends the returned transcript to `POST /api/extract` — exercising the real extraction, transcript caching, and quote verification engine.
6. Sends the approved card to `POST /api/cards` with the appropriate `expert_name`, `origin_tag` (Real or Demo), and `approved_by_expert: true`.
7. The script is idempotent: it checks whether a card with the same original audio hash already exists before creating duplicates.

This guarantees every seed card was produced by the same code path a real user would follow, and exercises the full pipeline during development.

---

## Important Failure Modes

- **Gemini Free-Tier Quota Depletion (HTTP 429) or Capacity Spike (HTTP 503):**
  *Fallback:* The backend retries with exponential backoff (up to 3 attempts per model), switches to the secondary Gemini model, and if still unavailable, immediately falls back to Groq `whisper-large-v3`. The frontend displays a visible badge: *"⚠ Transcribed via Groq fallback"*.
- **Hallucinated Field Extraction (AI invents a diagnostic procedure):**
  *Fallback:* The server runs Arabic-normalized substring matching (with lowercase Latin, length cap <= 60%, and cross-field duplicate rejection) to verify each reported verbatim quote against the approved transcript. If the quote cannot be verified, the field shows *"Could not be verified – please edit"* so the expert can manually correct it. This is distinct from *"Not mentioned"*, which is only used when the model itself reports nothing was stated.
- **Unclear Dialect Audio Words:**
  *Fallback:* The STT prompt mandates `[unclear]` tags instead of phonetic hallucination. The UI shows a count of `[unclear]` words above the transcript textarea, highlighted when > 0, for the expert to resolve before extraction.
- **ffmpeg Binary Not Found or Malformed Input:**
  *Fallback:* The `/api/transcribe` endpoint returns HTTP 500 with a clear message: *"ffmpeg binary not found. Please ensure imageio-ffmpeg is installed in requirements.txt"*. Files over 10 MB or 2 minutes are rejected with HTTP 400.
- **Search Query Unrelated to Existing Cards:**
  *Fallback:* Calibrated similarity threshold cleanly triggers the *"I don't know — no matching card found"* screen rather than surfacing irrelevant advice.

---

## What Was Simplified and Why

- **Local SQLite + File Storage instead of Cloud PostgreSQL + S3:**
  *Why:* Eliminates cloud hosting fees, authentication, and external network dependencies. Keeps the app completely local and operable on WSL2 for the demo video.
- **Character N-Gram TF-IDF instead of Vector Database / External Embeddings API:**
  *Why:* Operates offline with zero quota consumption, no embedding API costs, and predictable behavior. Character n-grams handle Arabic morphological variation without a stemmer. Embeddings kept as fallback only if held-out test results are poor.
- **Normalized Substring Quote Verification instead of Heavy NLI Model:**
  *Why:* Arabic-normalized substring check is 100% deterministic, instant, requires 0 API calls, and reliably catches hallucinated additions. The normalization handles diacritics, alef/ya/ta-marbuta variants, Latin case, and punctuation differences.
- **Single-Page Sequential Sections instead of Multi-Step Modal Wizard:**
  *Why:* Eliminates complex step-state-machine JavaScript. The contribution flow is a single scrollable page where sections unlock progressively (Setup → Capture → Transcript → Review). Simpler to build, debug, and demonstrate.
- **Plain RTL Textarea + `[unclear]` Counter instead of Rich Editor with Chip Highlights:**
  *Why:* A standard `<textarea>` is universally reliable for RTL text editing. An `[unclear]` word counter above it provides sufficient visibility without complex contentEditable DOM manipulation.
- **No Live Sound-Level Visualizer:**
  *Why:* Removing the real-time audio visualization (canvas/analyser node) significantly reduces frontend complexity without affecting core functionality. The elapsed timer and playback preview are sufficient for the POC.

---

## Decisions and Open Issues

### Decisions Made from Day-1 Transcription Gate & Build Preparation
1. **Multi-Tier STT Hierarchy:** Primary `gemini-3.8-flash`; Secondary `gemini-3.5-flash`; Tertiary Groq `whisper-large-v3`. All model names configurable via `.env`.
2. **Verbatim Prompting with `[unclear]` Tags:** Replaces guessing with explicit human review markers in the UI.
3. **Daily Cap Defense:** SHA-256 caching on original audio bytes + transcript-keyed extraction cache + distinct extraction models (`EXTRACTION_MODEL` and `EXTRACTION_FALLBACK_MODEL`) preserve the ~20 requests/day STT quota.
4. **Domain Glossary & Transliteration Aliases:** General oil & gas data engineering vocabulary included in prompt instructions. Search alias table reflects observed Whisper transliterations, but 16 evaluation queries must not rely on it.
5. **Quote-First Card Display:** Verbatim quotes are the primary display values on cards; summaries are secondary. Every field including `problem_summary` carries a verified quote.
6. **Quote Verification Integrity Rules:** Normalized substring matching with lowercase Latin, length <= 60% of transcript, and rejection of identical quotes across different fields. Two-tier outcome distinguishes *"Could not be verified – please edit"* from *"Not mentioned"*.
7. **Audio Conversion & Safe Execution:** ffmpeg converts audio via subprocess argument list (never shell); incoming bytes hashed before re-encoding; uploaded filename never used as filesystem path; strict 10 MB and 2 min limits.
8. **Seed Cards via Pipeline:** `scripts/seed_cards.py` reads from private `audio/` by default, copies to `samples/` only upon written consent, and sends audio through real API endpoints.
9. **Private Audio, Public Samples:** `audio/` is gitignored for all recordings; `samples/` holds only consented clips committed to the repo.

### Learner Uncertainty Clarified
- **Uncertainty:** Handling non-standard Libyan Arabic dialect combined with English technical terms without losing the technical meaning or hitting API budget walls.
- **Resolution:** Validated directly in the Day-1 gate. Gemini showed superior recognition of Latin technical terms (`accuracy`, `data leakage`, `stratified split`), while Groq provided an ultra-fast robust fallback. The character n-gram approach with alias expansion handles Arabic script variations of English terms (e.g. `نورميزايليشن` ↔ `normalization`) without needing a full Arabic NLP pipeline. Highlighting `[unclear]` tokens gives the expert transparent editorial control before structuring.
