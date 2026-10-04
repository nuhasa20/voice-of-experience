---
doc: scope
status: approved
---

# Voice of Experience (صوت الخبرة)

A voice-first knowledge preservation web application for oil and gas data analysts and data engineers that turns spoken troubleshooting wisdom into structured, expert-approved reference cards with an honest "I don't know" boundary.

## The Unique Kernel
- **Authentic Tacit Wisdom over Generic AI Advice:** Solutions originate from human voice recordings (in Libyan Arabic with technical terms or English), capturing nuanced diagnostic thinking, field checks, and cautions.
- **Pre-Recording Human Provenance:** The expert explicitly enters their name and selects the origin tag (**Real** vs. **Demo**) in a pre-recording form before capturing audio, ensuring test data is never presented as genuine field expertise:
  - **Real:** The speaker describes a problem they genuinely encountered and solved, in their own words.
  - **Demo:** Scripted, read from a prepared text, or synthetic voice.
- **Human-in-the-Loop Dialect Correction:** Because speech-to-text transcription of Libyan dialect mixed with English technical jargon will make mistakes, the expert reviews and edits the raw transcript before AI card extraction occurs.
- **Strict Anti-Hallucination ("I Don't Know"):** The system is not a conversational chatbot. If an apprentice's search query does not match an existing expert card above a calibrated relevance threshold, the app explicitly answers *"I don't know — no matching card found"* rather than inventing technical procedures.
- **Advisory Only:** The application provides read-only guidance; it never connects to, queries, or controls any operational systems.

## Who It's For
- **Primary User:** A newly hired data analyst or data engineer on an oil and gas team inheriting legacy telemetry pipelines, model evaluation workflows, well sensor logs, and field reporting tools when experienced colleagues move on.
- **What They Do Today (Working Assumption):** Under pressure, they ask busy senior colleagues or attempt trial-and-error with data preprocessing; whether they consult written documentation is an assumption to validate.
- **Expert Contributor:** Experienced data engineers, researchers, or the author recording 1–2 minute voice notes on recurring, generic data troubleshooting pitfalls.

## The Core Loop
1. **Pre-Record Setup:** Expert inputs their Name, selects Origin Tag (`Real` or `Demo`), confirms the consent checkbox (*"I agree to store my recording and allow it to be processed by an external AI service for transcription and structuring"*), and reads the confidentiality warning (*"Do not mention company system names, IP addresses, or passwords"*).
2. **Audio Capture:** Expert records a 1–2 minute voice note via live microphone.
3. **Transcript Review & Edit:** App generates a transcript; the expert fixes misheard dialect or technical terms.
4. **AI Extraction:** The AI extracts only five structured diagnostic fields:
   - Problem Summary
   - Possible Causes
   - Checks / Diagnostics
   - Solution Steps
   - Cautions (what not to do)
5. **Approve & Save:** Expert reviews the generated card fields, marks it **Expert-Approved**, and saves it. The audio file and structured card are persisted locally.
6. **Search & Playback:** A junior engineer types a plain-language question in Arabic or English.
   - If a card matches above the confidence threshold: displays the ranked card and plays the original voice recording.
   - If no card matches: cleanly responds *"I don't know — no matching card found"*.

## Key Risk to Test First (Day-1 Gate)
- **Transcription Feasibility Gate:** Transcribe 3 real Libyan Arabic audio recordings (with mixed English technical terms) through the candidate STT model/API *before* writing application code, to verify transcription quality and gauge the realistic extent of manual transcript editing needed.

## Inspiration & Identity
- **UI Language & Typography:** English interface labels and navigation; Arabic (RTL) card content and search inputs. Clean, high-contrast, technical aesthetic suitable for engineering teams.
- **Demo Video Subtitles:** The hackathon demo video will feature English subtitles over Arabic spoken recordings and interface demonstrations.
- **Tone:** Methodical, honest, safety-conscious.

## Why This Matters to the Learner
- Grounded directly in the learner’s professional background with oil and gas well monitoring data and machine learning workflows.
- Proves that an AI agent workflow can be guided with strict boundaries, secure handling, and human-in-the-loop validation for non-standard dialects.

## What "Working" Looks Like
A live demonstration proving the complete core loop:
1. Pre-recording setup with confidentiality banner and consent.
2. Recording a short Libyan Arabic voice note on a realistic data pitfall (e.g., merging unsynchronized sensor recordings).
3. Correcting dialect phrases in the raw transcript.
4. Extracting and approving the structured card with cautions and provenance badge.
5. Searching in natural language (Live Demo Example: *"القراءات جاية من حساسات مختلفة ومش مسجلة في نفس اللحظة"*) to pull up Card 2 and play the voice note.
6. **Acceptance Test for Anti-Hallucination:**
   - **Tuning Set (10 Queries):**
     - **5 In-Scope Queries (Paraphrased, distinct from chips and demo query):**
       1. *Libyan Arabic (Card 1):* "المودل يعطي دقة 99% في التدريب بس نتايجه كارثية لما نطبقه على بيانات جديدة"
       2. *Libyan Arabic (Card 2):* "الحساسات تسجل في أوقات متفرقة ودمج الصفوف مع بعض يعطي علاقات غلط"
       3. *English (Card 3):* "Kernel crashes with out of memory error when loading 10GB telemetry file"
       4. *English (Card 4):* "Field engineers at remote well pads cannot load weekly production summary without internet"
       5. *Mixed (Card 5):* "ملف واحد فيه صيغتين للتاريخ YYYY-MM-DD مع DD/MM/YYYY وقياسات بعد الصيانة الميدانية مش موثقة"
     - **5 Out-of-Scope Queries:**
       - Near-domain negative 1: "How to tune hyperparameters for gradient boosting"
       - Near-domain negative 2: "Power BI refresh error after changing data source"
       - Distant negative 1: "How do I replace a drill bit on a rig?"
       - Distant negative 2: "What is the average oil price today?"
       - Distant negative 3: "Write a python script to scrape news headlines"
   - **Held-Out Test Set (6 Queries - Frozen beforehand):**
     - Positive 1 (Card 1): "Future target values leaked into the training features before split"
     - Positive 2 (Card 2): "Sensor timestamps do not align across independent logging instruments"
     - Positive 3 (Card 5): "تضارب صياغة التواريخ في نفس الجدول مع قراءات شاذة بعد أعمال صيانة غير مسجلة"
     - Negative 1 (Near-domain): "How to calculate moving average in SQL window functions"
     - Negative 2 (Near-domain): "Exporting clean GeoJSON from ArcGIS well coordinates"
     - Negative 3 (Distant): "What is the weather forecast for Sebha next week?"
   - **Threshold Tuning:** Similarity cut-off is calibrated on the 10-query tuning set so all 5 in-scope queries score above the threshold and all 5 out-of-scope queries cleanly trigger the *"I don't know"* fallback screen.

## The POC Boundary

**Now (Proof of Concept):**
- Single-page application (English UI, Arabic RTL cards and search).
- Pre-recording metadata form (Expert Name, Real vs Demo tag, consent checkbox, confidentiality warning).
- In-browser live microphone recording.
- Raw transcript editor for Libyan Arabic dialect corrections.
- AI extraction of the 5 diagnostic card fields (with Cautions).
- Expert-Approved sign-off and local persistence (audio + JSON/database).
- Plain-language semantic/keyword search with calibrated "I don't know" threshold.
- 5 seed cards covering distinct data engineering topics:
  1. Data leakage in model evaluation
  2. Unsynchronized sensor measurements (readings taken at different moments merged as simultaneous)
  3. Limited compute environment (RAM exhaustion on large files)
  4. Reports that do not open offline (remote field access)
  5. Inconsistent dates and event logs (mixed YYYY-MM-DD and DD/MM/YYYY formats in same file, and tests right after unlogged maintenance)
  *(At least 3 cards originate from real recordings; scripted/synthetic recordings are strictly labeled Demo).*
- **Audio Storage & Privacy Boundary:** A small `samples/` directory holds only audio whose speaker provided explicit consent for public publication in the repository. All other recordings remain strictly local and gitignored.
- **Emergency Cutting Priority (if time runs short):**
  1. First cut: Field-level editing of the extracted card (expert accepts AI extraction as-is or re-extracts from transcript).
  2. Second cut: File upload fallback (live microphone recording only).
  *Note:* Live mic recording and transcript editing are core and will never be cut.

**Later (Post-Hackathon):**
- User accounts and role-based permissions (Admins, Experts, Apprentices).
- Automated scanner for accidental PII / IP address / password leaks.
- Feedback loop ("This solution helped me / did not work").
- Offline PWA / mobile field client.

**Explicitly Cut:**
- ❌ Direct integration or execution on actual servers, databases, or industrial systems (advisory only).
- ❌ Unbounded conversational chat or general AI question-answering.
- ❌ Multi-language automatic translation beyond mixed Arabic/English query matching.
- ❌ Production cloud infrastructure (runs locally in development mode for the POC).
