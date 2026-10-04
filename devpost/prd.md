---
doc: prd
status: approved
---

# Voice of Experience (صوت الخبرة) — Product Requirements

A voice-first knowledge preservation web application for oil and gas IT support engineers that captures spoken troubleshooting expertise in Libyan Arabic and English, extracts structured expert-approved diagnostic cards, and provides search with a strict "I don't know" anti-hallucination boundary.  
**Source:** `scope.md > # Voice of Experience` & `scope.md > The Unique Kernel`.

---

## 1. The Core Journey
1. **Arrival:** The engineer opens the application in desktop Chrome and sees a single unified screen with an advisory warning, a prominent search box with hint questions, and a library displaying the 5 pre-loaded seed cards.
2. **Search:** The engineer types a symptom in Arabic or English (or clicks an example hint) and presses Enter.
   - *If matching cards exist:* The library view is replaced with ranked matching cards (with a "Best match" tag on the top result). The user reviews diagnostic steps, checks, safety warnings, and listens to the expert's original voice recording.
   - *If no card matches:* A calm panel displays *"I don't know"*, explaining that the app only answers from genuine human recordings, with options to rephrase, browse all cards, or record an expert note.
3. **Contribution:** An experienced engineer clicks *"Record an expert note"*, opening a 4-step modal wizard:
   - **Step 1 (Setup):** Enters Name, selects Real vs. Demo tag, checks external AI processing consent, and reads the confidentiality warning.
   - **Step 2 (Record):** Records audio with live sound-level visual feedback; recording auto-stops at 2:00 minutes. The user listens to playback.
   - **Step 3 (Transcript):** Edits the speech-to-text transcript in an RTL box while listening to the audio player beside it, then triggers AI card extraction.
   - **Step 4 (Review):** Reviews the 5 extracted diagnostic fields (field editing is optional), marks the card **Expert-Approved**, and clicks Save.
4. **Completion:** The modal closes, and the newly created card immediately appears at the top of the library with its provenance badge and audio player.

---

## 2. Screens and Layout
A unified single-page application with an interactive modal wizard for contributions:

### 2.1 Main Surface (Search & Library)
- **Header:**
  - Application title: **صوت الخبرة — Voice of Experience**
  - Safety subtitle: *"Advisory only: never connects to or controls any operational system"*
- **Search Section:**
  - Large search input field (`[ اكتب المشكلة بلغتك... ]`)
  - Clickable example question chips (UI hints only; formal acceptance tests use separate paraphrased queries)
  - Search button and a *"Clear search"* button (visible when filtering)
- **Cards Library Section:**
  - Displays the 5 seed cards (or filtered search results)
  - Result counter (e.g., *"2 matching cards"*) when searching
- **Contribution Call-to-Action:**
  - Prominent primary action button: `[ 🎙 Record an expert note ]`

### 2.2 Contribution Modal (4-Step Wizard)
- Interactive overlay dialog with step progression indicator (`Step 1: Setup` → `Step 2: Record` → `Step 3: Transcript` → `Step 4: Review`).
- Accessible `Cancel` button on all steps (prompts for confirmation if audio has already been recorded).
- `Back` navigation supported between steps (returning from Step 4 to Step 3 and clicking "Extract card" prompts: *"This will replace your edits to the card fields"*).

---

## 3. Look and Feel
- **Theme & Target Platform:** Clean, high-contrast industrial light theme designed strictly for desktop Chrome. Mobile layout is explicitly not a goal.
- **Palette & Contrast:**
  - Background: Warm light gray (`#F4F4F6` / `#F8F9FA`).
  - Primary text: Deep dark navy (`#0F172A`).
  - Interactive elements (buttons, links): Deep Teal (`#0F766E`).
  - Safety & Warnings: Reserved Amber (`#B45309`) — used exclusively for human-stated safety cautions ("amber means caution").
  - Provenance Badges:
    - **Real:** Green badge with visible text label `[Real]` (self-declared by speaker).
    - **Demo:** Neutral gray badge with visible text label `[Demo]`.
  - **Contrast Standard:** WCAG AA contrast (4.5:1) for text, checked with a contrast tool, including text against the warm gray background.
- **Typography:**
  - English UI labels and structure: **IBM Plex Sans**.
  - Arabic dialect content and search: **IBM Plex Sans Arabic**, sized comfortably for technical reading.
  - Bidirectional layout: English UI shell is LTR; search box, transcript editor, and card diagnostic content are RTL.
  - Layout resilience: Long text, technical abbreviations, and mixed Arabic/English phrases with numbers must wrap cleanly without breaking card containers or modal boundaries.

---

## 4. Features and Detailed Behaviors

### 4.1 Cards Library & Display
- **Default Compact View:**
  - Each card shows:
    - **Provenance Badge:** `[Real]` or `[Demo]` reflecting true origin (scripted/synthetic recordings are strictly labeled `[Demo]`).
    - **Expert Name:** Contributor's self-declared name.
    - **Audio Player:** Inline play/pause with duration readout (e.g., `1:15`).
    - **Problem Summary:** Clear problem title in the language of the recording.
    - **Safety Caution (Permanent):** One concise line of caution visible even when collapsed. If the human stated no caution, shows *"No caution stated by the expert"* in neutral styling (no amber).
    - **"Show details" Toggle:** Expands/collapses the full card.
- **Expanded Card View:**
  - Displays the 5 diagnostic fields:
    - Possible Causes
    - Diagnostic Checks
    - Solution Steps
    - Full Safety Warnings & Cautions
    - Provenance Attribution: *"Structured by AI from the expert's recording, approved by the expert."*
- **Seed Cards Requirement:**
  - Library ships with 5 seed cards covering distinct, non-competing oil & gas IT support topics:
    1. Field network / telemetry drop
    2. Sensor data logging service stalled
    3. Corrupted backup archive
    4. Sensor calibration drift
    5. Local server / database connection failure
  - At least 3 cards originate from real human voice recordings. All seed cards are created through the application's own contribution wizard.

### 4.2 Search & "I Don't Know" Anti-Hallucination Fallback
- **Search Execution:** Triggered by typing and pressing Enter or clicking Search.
- **Matching Results State:**
  - Replaces library with ranked matching cards ordered closest to least close.
  - Result count header (e.g., *"Found 2 matching cards"*).
  - Prominent **"Best match"** label on the top-ranked card.
  - **No Numeric Scores:** Similarity percentages are hidden to prevent false precision.
  - Includes a **"Clear search"** button returning to the full library.
- **The "I Don't Know" Fallback State:**
  - Triggered strictly when no card scores above the calibrated relevance threshold. No separate ambiguity logic is implemented in the POC.
  - Calm neutral panel (no red error styling) displaying:
    - Heading: *"I don't know"*
    - Text: *"No expert card matches this problem. This application only answers from recordings by real people and never guesses."*
    - Suggestion: *"Try describing your symptom differently or checking keywords."*
    - Action 1: *"Browse all cards"* (clears search and restores the full library).
    - Action 2: *"Record an expert note"* (opens the contribution wizard).

### 4.3 Contribution Wizard (4 Steps)
- **Step 1: Setup**
  - Inputs: Expert Name (text), Origin Tag (radio: Real vs Demo with short definitions), and Consent Checkbox:
    - Consent text: *"I agree to store my recording and allow it to be processed by an external AI service for transcription and structuring."*
  - Prominent Confidentiality Warning: *"Do not mention company system names, IP addresses, or passwords."*
  - Validation: "Continue to Record" remains disabled until Name is filled, a tag is selected, and consent is checked.
- **Step 2: Record**
  - Big Record/Stop button, elapsed time counter, and real-time visual sound-level indicator.
  - Maximum duration: 2:00 minutes. Recording auto-stops at 2:00 with a clear notification: *"Maximum recording length of 2 minutes reached."*
  - Post-recording actions: Listen to playback, "Re-record", or "Continue to Transcript".
- **Step 3: Transcript Editor**
  - STT text appears in an editable RTL text box with an audio player placed beside it for simultaneous listening and dialect correction.
  - Extraction Action: "Extract card" button sends the transcript to the AI.
  - **Extraction Rules:**
    - AI extracts only what is stated in the transcript; it must never inject outside knowledge.
    - Any field not mentioned by the expert is explicitly marked *"Not mentioned"* and left empty.
    - If the transcript contains only small talk or lacks troubleshooting substance, no card is created; shows *"No troubleshooting content found"* with options to edit transcript or re-record.
- **Step 4: Review & Approval**
  - Shows the 5 extracted fields with header: *"Structured by AI from the expert's recording"*.
  - Field-level editing is optional in the POC; clicking **"Approve & Save"** is required.
  - Saves audio and card to persistent local storage, closes modal, adds new card to top of library, and displays a temporary success message.

---

## 5. States and Boundaries

### 5.1 System & Surface States
- **Empty Library State:** If no cards exist in the database, shows: *"No cards yet — record the first one"* with a button to open the contribution wizard.
- **Loading States:** Explicit, accessible loading spinners/indicators for:
  - Transcribing audio (Step 2 → Step 3)
  - Extracting structured card (Step 3 → Step 4)
  - Searching the card database
- **Empty Search Input State:** Pressing Enter on an empty box displays a gentle inline hint (*"Describe the problem you're facing"*) and keeps the full library visible. It is never treated as "I don't know".
- **Hardware / Device States:**
  - *Microphone Blocked:* Displays browser permission instructions (click lock icon, allow microphone, reload) + "Try again" button. Preserves Step 1 inputs.
  - *No Microphone Found:* Distinct message explaining no input device was detected on the system.
  - *Silent / Insufficient Audio (< 5 seconds or silent):* Displays *"We couldn't hear enough speech. Check your microphone and try again"*, offering Re-record. Nothing is sent to AI.
- **Service Failure State:** If STT, LLM extraction, or search fails, displays: *"Something went wrong on our side, not because there's no answer"*, retaining user audio and input with a "Try again" option.

### 5.2 Persistence & Privacy Boundaries
- **Local Persistence:** All approved cards, edited transcripts, and audio files persist across page refreshes and application restarts.
- **Repository & Video Publication Boundary:** In-app consent covers only local processing and AI transcription/extraction. It does **not** authorize publishing audio in the public GitHub repository or the demo video; any audio committed to `samples/` or featured in the public video requires separate, explicit written consent from the speaker. All other audio remains strictly local and gitignored.

---

## 6. Acceptance Criteria & Test Sets

- **Anti-Hallucination Retrieval Acceptance Test:**
  - **10-Query Tuning Set:**
    - 5 In-scope queries (one per seed card: 2 in Libyan Arabic, 2 in English, 1 mixed; all natural paraphrases, not copied from card text) must retrieve their correct card.
    - 5 Out-of-scope queries (including 2 near-domain negatives such as *"Reset SAP HR password"*, *"Configure Outlook email on mobile"*, and 3 distant negatives such as *"How do I replace a drill bit?"*) must score below threshold and cleanly trigger *"I don't know"*.
  - **Held-Out Test Set (6 Queries):**
    - 3 Positive and 3 Negative queries (including at least one near-domain negative) written beforehand, frozen, and evaluated without modification. Results reported as observed.
  - **Threshold Policy:** Calibrated on the 10-query tuning set so all 5 in-scope queries pass and all 5 out-of-scope queries fail.
- **Contribution Acceptance Criteria:**
  - Cannot proceed past Step 1 without name, origin tag, and consent.
  - Live sound meter visibly responds to ambient speech.
  - Audio auto-stops at 2:00 minutes. Audio under 5s or silent is rejected before AI calls.
  - Transcript editor allows direct manual correction of Arabic dialect text.
  - Unmentioned fields are cleanly labeled *"Not mentioned"*.
  - Approving a card immediately displays it in the library with audio playback and provenance tag.
  - **End-to-End Demo Path:** The full demo path from `scope.md` executes end to end in one continuous session with zero manual database or file interventions.
  - **Persistence:** Approved cards and audio remain fully accessible and playable after browser refresh or app restart.

---

## 7. Product Decisions & Known Limitations

1. **Self-Declared Provenance:** The `[Real]` vs. `[Demo]` tag is self-declared by the contributor and is not independently verified by software.
2. **Definition of "Expert-Approved":** Sign-off verifies only that the human contributor approved the extracted card text, not that the technical troubleshooting steps are certified correct.
3. **No General Chatbot:** Queries only retrieve human-approved cards; no LLM generates answers on the fly.
4. **Desktop Chrome Only:** Optimized exclusively for desktop Chrome; mobile responsive view is explicitly out of scope.
5. **Known Limitation (Deletion):** Self-service *"Delete my recording"* is deferred to a future release; cards must be deleted manually from the local data file if necessary.

---

## 8. Non-Goals (Explicitly Cut)
- ❌ Direct execution or network connection to real industrial/IT systems (advisory only).
- ❌ Open-ended conversational chat or general AI question answering.
- ❌ Automated multi-language translation beyond mixed Arabic/English query matching.
- ❌ Production cloud deployment (runs locally in development mode).
- ❌ Mobile responsive layout.
