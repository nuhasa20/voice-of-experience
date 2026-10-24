# Voice of Experience (صوت الخبرة)

**Voice-first engineering knowledge preservation for industrial troubleshooting in oil & gas facilities.**

---

## Overview & Target Audience

In upstream and midstream oil & gas operations, high-value diagnostic knowledge is often trapped in informal phone calls, field voice notes, or senior operator intuition. Traditional computerized maintenance management systems (CMMS) often contain sparse, sanitized records that fail to convey the subtle operational reasoning needed to troubleshoot complex equipment and data anomalies.

**Voice of Experience (صوت الخبرة)** is built for **data analysts, production engineers, and plant operators** working in industrial oil & gas environments. It provides a voice-first workflow to record, transcribe, structure, verify, and retrieve operational troubleshooting notes spoken in natural Libyan Arabic dialect mixed with English technical terms.

---

## The Problem

When production anomalies occur—such as sensor drift masquerading as well drawdown, deep learning models failing on rare fault distributions, or models performing well on simulators but collapsing on real field data—junior engineers and data analysts often lack access to experienced mentors. Existing LLM-based solutions frequently hallucinate plausible-sounding but hazardous advice in safety-critical industrial settings.

---

## How It Works

Voice of Experience enforces an end-to-end, safety-conscious workflow:

1. **Audio Capture (Voice Note or Upload)**
   - Speak naturally in Libyan Arabic dialect interspersed with English technical engineering terms (up to 2 minutes / 10 MB).
   - Alternatively, upload existing `.ogg`, `.webm`, `.wav`, or `.mp3` voice recordings.
2. **Verbatim Transcript Review & Dialect Correction**
   - Resilient speech-to-text pipeline transcribes the audio.
   - The user reviews the exact verbatim transcript and resolves any flagged `[unclear]` tokens directly in the editor before structured extraction.
3. **5-Field Structured Diagnostic Card**
   - AI extracts five operational fields:
     - **Problem Summary**
     - **Possible Causes**
     - **Verification Checks**
     - **Solution Steps**
     - **Cautions & Warnings**
4. **Code-Enforced Verbatim Quotes Verification**
   - Pure Python string normalization and substring matching verifies that every quote extracted by the model appears literally in the reviewed transcript.
   - Any quote containing unresolved `[unclear]` markers is strictly rejected by the verification engine.
5. **Human Expert Approval**
   - The card cannot be added to the searchable knowledge library until an authorized expert explicitly verifies the content and checks the approval box.
6. **Search with an Honest "I Don't Know"**
   - Users search by symptoms or equipment behavior using Arabic or English technical phrasing.
   - The retrieval engine uses character n-gram TF-IDF cosine similarity to handle dialectal spelling variations and transliterated technical terms.
   - When the best matching score falls below the calibrated similarity threshold ($\tau = 0.19$), the system refrains from generating unverified text and presents an honest fallback:
     > *"I don't know — no expert has covered this yet. We only show answers recorded and approved by an expert."*

---

## Real vs Demo Labels

Every diagnostic card in the database is explicitly labeled:
- **`Real`**: Notes recorded from real-world oil & gas facilities, actual well monitoring systems, and verified plant operations.
- **`Demo`**: Synthetic, simulated, or educational troubleshooting scenarios.

Labels are prominently displayed across the card library and search result cards to ensure complete provenance and prevent synthetic cases from masquerading as plant operating records.

---

## How to Run

### Prerequisites
- Python 3.10+
- `ffmpeg` (for audio transcoding to OGG Opus)

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/nuhasa20/voice-of-experience.git
cd voice-of-experience
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and insert your API keys:

```bash
cp .env.example .env
```

Open `.env` and fill in:
- `GEMINI_API_KEY`: Google Gemini API key (for primary STT and card extraction).
- `GROQ_API_KEY`: Groq API key (for Whisper fallback STT).

### 3. Run the Application

```bash
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Open your browser at `http://127.0.0.1:8000`.

---

## Running Tests

The test suite validates database integrity, audio conversion, transcription pipelines, quote verification algorithms, search ranking, and DOM bindings:

```bash
python3 -m pytest tests/ -v
```

---

## Search Evaluation Results

Search performance is systematically evaluated using `scripts/eval_search.py` on `eval/queries.json`:

- **Tuning Split (10 queries)**:
  - **9/10 passed** at calibrated threshold $\tau = 0.19$.
  - Includes one false positive on query **T9** (*"المضخة الغاطسة حرارة المحرك مرتفعة، ايش السبب"*, an out-of-corpus near-domain negative that scored 0.22 against unrelated pump notes), illustrating the precision trade-off in small corpora.
- **Held-Out Split (7 queries)**:
  - **7/7 passed (100%)**, evaluated exactly once with no post-hoc threshold adjustment.
  - *Note*: Query **H4**'s ground truth was updated prior to the held-out evaluation when a matching diagnostic card (`card_11b4100a67b8`, addressing single-point LSTM remaining useful life predictions) was recorded and added to the library.

To re-run evaluation:
```bash
python3 scripts/eval_search.py --split tuning
python3 scripts/eval_search.py --split heldout
```

---

## Limitations

- **Internet & Free-Tier Quotas**: Requires an active internet connection to communicate with Gemini and Groq API endpoints. Free-tier accounts may be subject to rate limits during peak usage.
- **Small Corpus Size**: The initial knowledge library contains a curated proof-of-concept corpus of 7 verified diagnostic cards.
- **STT Fallback Chain**: Speech-to-text relies on a cascade (`gemini-3.8-flash` $\rightarrow$ `gemini-3.5-flash` $\rightarrow$ Groq `whisper-large-v3`). In the event of network disruption or concurrent rate limits across all providers, transcription will fail gracefully with a descriptive error.
- **Browser Compatibility**: Google Chrome is recommended for audio recording to guarantee standard `MediaRecorder` WebM/Opus support.

---

## Credits & Attributions

- Search pill input styling inspired by [Uiverse.io](https://uiverse.io/) design by **Smit-Prajapati**, adapted to the project's industrial teal aesthetic and Arabic/English bidirectional layout.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.  
Copyright (c) 2026 **Nuha Alqaweedhi**.
