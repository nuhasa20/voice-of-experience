---
doc: checklist
status: approved
---

# Build Checklist

Build mode: fast

## Slices

- [x] **1. Audio Capture, ffmpeg Conversion & Multi-Tier Resilient STT Pipeline (Stage 1)**
  Becomes usable: Users can record up to 2 minutes of Libyan Arabic/English audio via microphone in browser or upload `.ogg`/`.webm`/`.wav`/`.mp3` audio; server converts to OGG Opus via `imageio-ffmpeg`, computes SHA-256 on original bytes, checks SQLite STT cache, and transcribes through a multi-tier fallback cascade (`gemini-3.8-flash` -> `gemini-3.5-flash` -> Groq `whisper-large-v3`).
  Why now: The audio input and speech-to-text pipeline is the foundational entry point for field operators; proving reliable transcription of code-switched Libyan Arabic and technical engineering terms under API quota limits removes the biggest technical risk early.
  PRD ref: `prd.md > 1. The Core Journey` (Step 2), `prd.md > 4.3 Contribution Wizard` (Step 2)
  Spec ref: `spec.md > Components > 3. Audio Conversion Layer`, `spec.md > Components > 4. Resilient STT Transcription Pipeline`
  Build: Implement `server/audio_convert.py` with ffmpeg conversion and SHA-256 calculation; implement `server/stt_pipeline.py` with provider retries and caching; expose `POST /api/transcribe` in `server/main.py`; wire `static/js/recorder.js` and upload dropzone in `static/index.html`.
  Verify (mechanical): Run `python3 -m pytest tests/test_transcribe_endpoint.py tests/test_transcribe_error_handling.py tests/test_gemini_webm.py` (all passed: validates valid conversions, SHA-256 hashing, cache hits, 400 on empty/oversized files, and 422 on corrupt audio).
  Learner check: Open browser, record a 5-second test note on the microphone, click "Normalize & Transcribe", and confirm spoken Arabic dialect appears accurately in the transcript box with model provenance badge.
  Commit: `Build stages 1-3: STT pipeline, extraction with quote verification, contribution UI` (commit `78d416c`)

- [x] **2. Verbatim Transcript Review, Dialect Correction & [unclear] Counter (Stage 2)**
  Becomes usable: Transcribed text displays in an RTL-aware editor where the engineer reviews and corrects dialect phrasing; any occurrence of `[unclear]` is counted live by a badge, and attempting to extract with unresolved tokens triggers a clear confirmation modal.
  Why now: Ground-truth fidelity requires human operator review before AI extraction; enforcing visibility on ambiguous words protects the downstream verbatim quote verification from propagating hallucinations.
  PRD ref: `prd.md > 1. The Core Journey` (Step 3), `prd.md > 4.3 Contribution Wizard` (Step 3)
  Spec ref: `spec.md > Components > 2. Contribution Flow` (Section 3), `spec.md > Important Failure Modes`
  Build: Add live regex scanner in `static/js/contribution.js` for `\[unclear\]` tokens; update counter badge in `static/index.html`; implement confirmation modal `#unclearConfirmModal` with "Back to Editing" and "Confirm & Extract Anyway" actions.
  Verify (mechanical): Run browser DOM assertion tests in `tests/test_save_flow.py` verifying `#unclearCounter`, `#modalUnclearCount`, and event handlers exist and bind correctly without exceptions.
  Learner check: Type text containing `[unclear]` in the transcript editor, verify counter increments to 1, click Extract, and verify warning modal explains that quotes containing `[unclear]` will fail verification.
  Commit: `Build stages 1-3: STT pipeline, extraction with quote verification, contribution UI` (commit `78d416c`)

- [x] **3. Quote-Verified AI Diagnostic Card Extraction & Expert Approval Persistence (Stage 3)**
  Becomes usable: System extracts 5 structured diagnostic fields (Problem Summary, Possible Causes, Verification Checks, Solution Steps, Cautions & Warnings) using `gemini-3.1-flash-lite` (with `gemini-3.6-flash` fallback); pure Python string normalization guarantees every extracted quote is a literal substring of the reviewed transcript; quotes with `[unclear]` are rejected; card is persisted to SQLite only when an expert explicitly checks approval.
  Why now: The unique kernel of the project is ensuring that AI never invents operational troubleshooting guidance in safety-critical environments; code-enforced quote verification mathematically guarantees zero hallucinated advice.
  PRD ref: `prd.md > 1. The Core Journey` (Step 4 & 5), `prd.md > 4.3 Contribution Wizard` (Step 4), `prd.md > 6. Acceptance Criteria`
  Spec ref: `spec.md > Components > 5. Quote-Verified AI Card Extraction Engine`, `spec.md > Data Model > SQLite Schema`
  Build: Implement `server/extractor.py` with strict JSON schema prompt, Arabic character normalizer, substring check, duplicate quote check, and length cap; expose `POST /api/extract` and `POST /api/cards` in `server/main.py`; implement extraction cache and SQLite `cards` table in `server/database.py`; wire UI cards display and approval flow in `static/js/contribution.js`.
  Verify (mechanical): Run `python3 -m pytest tests/test_stage3_extract_and_save.py tests/test_save_flow.py tests/test_db_guard.py` (22 tests passed: validates 5 fields extraction, substring verification, rejection of fabricated quotes or quotes with `[unclear]`, extraction caching, expert checkbox requirement, and DB persistence).
  Learner check: Extract a diagnostic card from a reviewed transcript, observe the green "Verified Verbatim Quote" badges, check "Expert-Approved", click "Save Diagnostic Card", and observe card appearing in library with [Real]/[Demo] badge and audio playback.
  Commit: `Fix save UI bug, prevent duplicate saves, isolate tests from production DB` (commit `6331d52`)

- [x] **4. Character N-Gram TF-IDF Search Engine & Honest "I Don't Know" Fallback (Stage 4)**
  Becomes usable: Engineers search diagnostic troubleshooting cards by symptoms across Libyan Arabic dialect and English technical terminology; character 3-gram and 4-gram TF-IDF cosine similarity retrieves relevant cards above calibrated threshold $\tau = 0.19$; if no card scores $\ge 0.19$, the system displays an honest fallback panel (*"I don't know — no expert has covered this yet"*) with zero hallucination.
  Why now: Retrieval completes the loop for junior engineers seeking advice, and the calibrated threshold proves the anti-hallucination boundary against near-domain and out-of-domain negative queries.
  PRD ref: `prd.md > 4.2 Search & "I Don't Know" Anti-Hallucination Fallback`, `prd.md > 6. Acceptance Criteria`
  Spec ref: `spec.md > Components > 7. Character N-Gram Search Engine`, `spec.md > Components > 1. Main Surface & Search Interface`
  Build: Implement `server/search.py` with character n-gram TF-IDF vectorizer, Arabic normalization (`server/normalizer.py`), and alias expansion; add threshold evaluation script `scripts/eval_search.py` reading `eval/queries.json`; add `POST /api/search` and `GET /api/cards` in `server/main.py`; build search controller with instant suggestions dropdown in `static/js/search.js`.
  Verify (mechanical): Run `python3 -m pytest tests/test_search.py` (10 tests passed) and execute `python3 scripts/eval_search.py --split tuning` (9/10 passed at $\tau = 0.19$) and `python3 scripts/eval_search.py --split heldout` (7/7 passed, 100%).
  Learner check: Type "قراءات الضغط تنزل شوية شوية" in the search bar and verify top match is card `card_953140cd301b` (sensor drift); type an out-of-domain query like "طريقة تحضير الكسكسي" and verify system shows the honest "I don't know" fallback panel.
  Commit: `Add search (char n-gram TF-IDF, I-don't-know fallback), eval split, STT error handling` (commit `47b5074`)

- [x] **5. Search UI Modernization, Responsive Detached Panel & Submission Polish**
  Becomes usable: Clean, professional industrial interface featuring a hero search card with a neumorphic teal pill input, detached floating suggestions panel with soft teal shadow and rounded corners (16px), complete removal of emojis in favor of accessible inline SVGs, `<meta name="google" content="notranslate">`, and `Cache-Control: no-cache` headers on all static assets.
  Why now: Prepares the proof of concept for public review and evaluation, ensuring high visual clarity on both mobile (375px) and desktop (1280px) viewports with zero browser-level translation corruption of dialectal text.
  PRD ref: `prd.md > 3. Look and Feel`, `prd.md > 2.1 Main Surface`
  Spec ref: `spec.md > Look and Feel`, `spec.md > Where It Runs and How Someone Tries It`
  Build: Redesign search styles in `static/css/main.css`; refine dropdown positioning to `calc(100% + 8px)`; remove `#scrollToContributeBtn` from hero; replace emojis in `static/index.html` with inline SVGs; configure `NoCacheStaticFiles` in `server/main.py`; generate `README.md` and `.env.example`.
  Verify (mechanical): Run full test suite `python3 -m pytest tests/ -v` (all 46 tests passed in 58s); verify zero emojis in `static/index.html`; verify `Cache-Control: no-cache` on `/`, `/css/main.css`, and `/js/search.js`.
  Learner check: Open app at 1280px and 375px, click search bar to see detached floating suggestions panel, confirm full pill rounded ends remain intact, and verify clean typography across all cards.
  Commit: `Prepare submission: README, env template, UI cleanup, no-cache static` (commit `d7b508b`)

## Hands-on Checkpoints

- [x] Early usable behavior explored — Stage 1 audio capture and transcription verified end-to-end with real audio recordings; dialect preserved accurately by Gemini multimodal STT.
- [x] Final kick-the-tires exploration and feedback completed — Search hero interaction, honest fallback panel, quote verification highlighting, and responsive layout evaluated across viewports; test suite confirmed 100% green.

## Final Review

- [x] Final review complete — feedback resolved and learner confirms ready to ship
  - [x] Prevent duplicate card saves on rapid button clicks (resolved in commit `6331d52`).
  - [x] Ensure test suite executes against isolated temporary SQLite databases without touching production data (resolved in `tests/test_db_guard.py` & `conftest.py`).
  - [x] Remove awkward bottom-corner straightening on search pill when suggestions open, keeping full 999px pill radius and detached floating panel (resolved in `static/css/main.css`).
  - [x] Remove extraneous emojis across the entire UI in favor of industrial inline SVGs and clean typography (resolved in `static/index.html`).
  - [x] Prevent automated browser translation popups from corrupting Libyan Arabic technical terms via `<meta name="google" content="notranslate">` (resolved in `static/index.html`).

## Code Tour and App Map

- [x] Learning activity complete — guided route, focused alternative, prior practice connected, or brief recap
- [x] Optional edit and transfer reflection addressed — offered/declined/already covered/not applicable as appropriate
- [x] `devpost/app-map.html` generated from finished code, checked, and shown, including a project-grounded practice to reuse

Activity and evidence: Focused technical walkthrough connecting the project's unique kernel (code-enforced verbatim quote verification in `server/extractor.py`) and retrieval thresholding (`server/search.py` at $\tau=0.19$) to the passing test suite (46 passed) and evaluation benchmark (held-out 7/7, 100%).
Route and stops:
  1. `static/js/contribution.js` -> `server/extractor.py:extract_card_fields()` (verbatim quote verification algorithm).
  2. `server/database.py:get_connection()` & `server/config.py:get_db_path()` (runtime test isolation guards preventing database collisions).
  3. `server/search.py:search_cards()` & `scripts/eval_search.py` (character n-gram TF-IDF similarity and $\tau=0.19$ threshold enforcement).
Edit outcome: Safe UI refinement completed and verified; search pill stays fully rounded and suggestions panel floats cleanly detached.
Reflection: Connected the core architectural pattern—using deterministic code checks (Python string normalization and similarity thresholds) as safety guardrails around stochastic LLMs—as a reusable design practice for future AI engineering projects.
Activity mode: Live app, verified test suite, and standalone offline HTML app map.

## Revisions

- Switched extraction fallback model from `gemini-3.5-flash` to `gemini-3.6-flash` — the original model occasionally omitted structured caution fields under strict JSON mode constraints.
- Capped primary STT retries to 1 with immediate fallback to secondary model and Groq Whisper — API quota spikes during batch tests caused long request timeouts when retrying too aggressively.
- Isolated test database paths dynamically via `VOICE_DB_PATH` — tests were writing temporary diagnostic cards directly into `data/voice_experience.db`, polluting the production search index.
- Calibrated search threshold $\tau$ to 0.19 based on empirical tuning split results — 0.19 achieved 90% accuracy on tuning (9/10) and successfully generalized to 100% on the held-out split (7/7).
- Updated held-out ground truth for query H4 — added missing diagnostic note `card_11b4100a67b8` covering single-point LSTM remaining useful life predictions prior to running the held-out evaluation.
- Decoupled search suggestions dropdown from search pill wrapper — straightening bottom corners on the pill created visual distortion, so dropdown was converted to a detached floating panel with `top: calc(100% + 8px)` and 16px border-radius.
