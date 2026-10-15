/**
 * Voice of Experience (صوت الخبرة) — Contribution Flow
 *
 * Each ContributionWizard instance holds ALL its state internally.
 * No shared global variables. After Save the wizard fully resets so a
 * second card can be submitted cleanly.
 */

import { AudioCaptureManager } from './recorder.js';

export class ContributionWizard {
  constructor() {
    this.audioManager = new AudioCaptureManager({
      maxDurationSec: 120,
      onTick: (secs, formatted) => this.updateTimerDisplay(formatted),
      onStateChange: (state, data) => this.handleAudioStateChange(state, data),
      onMaxDurationReached: () => this.showToast('Maximum recording length of 2 minutes reached.', 'warning'),
    });

    // ── Per-contribution state ────────────────────────────────────────────
    this.currentAudioPayload   = null;  // { file, blob, url }
    this.transcriptionResult   = null;  // { audio_hash, transcript, stt_provider, cached, fallback, duration }
    this.extractionResult      = null;  // { fields, model_name, cached }
    // ─────────────────────────────────────────────────────────────────────

    this.initDOMElements();
    this.bindEvents();
    this.validateSetupForm();
  }

  // =========================================================================
  // DOM initialisation
  // =========================================================================
  initDOMElements() {
    // Setup
    this.expertNameInput   = document.getElementById('expertName');
    this.originRadios      = document.querySelectorAll('input[name="originTag"]');
    this.consentCheckbox   = document.getElementById('consentCheckbox');
    this.setupContinueBtn  = document.getElementById('setupContinueBtn');

    // Sections
    this.sectionSetup      = document.getElementById('sectionSetup');
    this.sectionCapture    = document.getElementById('sectionCapture');
    this.sectionTranscript = document.getElementById('sectionTranscript');
    this.sectionReview     = document.getElementById('sectionReview');

    // Step indicators
    this.stepIndicators = {
      1: document.getElementById('stepIndicator1'),
      2: document.getElementById('stepIndicator2'),
      3: document.getElementById('stepIndicator3'),
      4: document.getElementById('stepIndicator4'),
    };

    // Capture — Record tab
    this.recordBtn         = document.getElementById('recordBtn');
    this.recordTimer       = document.getElementById('recordTimer');
    this.recordStatusText  = document.getElementById('recordStatusText');
    this.recordPreviewBox  = document.getElementById('recordPreviewBox');
    this.recordAudioPlayer = document.getElementById('recordAudioPlayer');
    this.rerecordBtn       = document.getElementById('rerecordBtn');

    // Capture — Upload tab
    this.fileDropzone      = document.getElementById('fileDropzone');
    this.audioFileInput    = document.getElementById('audioFileInput');
    this.uploadPreviewBox  = document.getElementById('uploadPreviewBox');
    this.uploadAudioPlayer = document.getElementById('uploadAudioPlayer');
    this.uploadFileName    = document.getElementById('uploadFileName');
    this.uploadFileSize    = document.getElementById('uploadFileSize');
    this.clearUploadBtn    = document.getElementById('clearUploadBtn');

    // Capture — tabs & shared
    this.captureTabRecord  = document.getElementById('captureTabRecord');
    this.captureTabUpload  = document.getElementById('captureTabUpload');
    this.recordBoxCard     = document.getElementById('recordBoxCard');
    this.uploadBoxCard     = document.getElementById('uploadBoxCard');
    this.transcribeBtn     = document.getElementById('transcribeBtn');
    this.captureLoading    = document.getElementById('captureLoading');
    this.captureErrorBanner= document.getElementById('captureErrorBanner');
    this.captureErrorMsg   = document.getElementById('captureErrorMsg');

    // Transcript section
    this.transcriptEditor      = document.getElementById('transcriptEditor');
    this.unclearCounter        = document.getElementById('unclearCounter');
    this.unclearCountNumber    = document.getElementById('unclearCountNumber');
    this.unclearCounterText    = document.getElementById('unclearCounterText');
    this.transcriptAudioPlayer = document.getElementById('transcriptAudioPlayer');
    this.sttProviderBadge      = document.getElementById('sttProviderBadge');
    this.sttFallbackBanner     = document.getElementById('sttFallbackBanner');
    this.sttCachedBadge        = document.getElementById('sttCachedBadge');
    this.wordCountDisplay      = document.getElementById('wordCountDisplay');
    this.extractCardBtn        = document.getElementById('extractCardBtn');
    this.startOverBtn          = document.getElementById('startOverBtn');

    // Review / Section 4
    this.extractionLoading       = document.getElementById('extractionLoading');
    this.extractionErrorBanner   = document.getElementById('extractionErrorBanner');
    this.extractionErrorMsg      = document.getElementById('extractionErrorMsg');
    this.extractionMetaBar       = document.getElementById('extractionMetaBar');
    this.extractionModelBadge    = document.getElementById('extractionModelBadge');
    this.extractionCachedBadge   = document.getElementById('extractionCachedBadge');
    this.extractedFieldsContainer= document.getElementById('extractedFieldsContainer');
    this.cardApprovalActions     = document.getElementById('cardApprovalActions');
    this.expertApprovalCheckbox  = document.getElementById('expertApprovalCheckbox');
    this.saveCardBtn             = document.getElementById('saveCardBtn');
    this.saveLoading             = document.getElementById('saveLoading');
    this.saveSuccessBanner       = document.getElementById('saveSuccessBanner');
    this.backToTranscriptBtn     = document.getElementById('backToTranscriptBtn');

    // Unclear confirmation modal
    this.unclearConfirmModal     = document.getElementById('unclearConfirmModal');
    this.modalUnclearCount       = document.getElementById('modalUnclearCount');
    this.modalCancelBtn          = document.getElementById('modalCancelBtn');
    this.modalConfirmBtn         = document.getElementById('modalConfirmBtn');

    // Toast container
    this.toastContainer = document.getElementById('toastContainer');
  }

  // =========================================================================
  // Event binding
  // =========================================================================
  bindEvents() {
    // Section 1
    this.expertNameInput.addEventListener('input', () => this.validateSetupForm());
    this.originRadios.forEach(r => r.addEventListener('change', () => this.validateSetupForm()));
    this.consentCheckbox.addEventListener('change', () => this.validateSetupForm());
    this.setupContinueBtn.addEventListener('click', () => {
      this.activateSection(2);
      this.sectionCapture.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    // Capture tab switching
    this.captureTabRecord.addEventListener('click', () => this.setCaptureMode('record'));
    this.captureTabUpload.addEventListener('click', () => this.setCaptureMode('upload'));

    // Record handlers
    this.recordBtn.addEventListener('click', () => this.toggleRecording());
    this.rerecordBtn.addEventListener('click', () => {
      this.audioManager.reset();
      this.recordPreviewBox.style.display = 'none';
      this.recordStatusText.textContent = 'Click to record your voice';
      this.recordTimer.textContent = '00:00';
      this.currentAudioPayload = null;
      this.updateTranscribeButtonState();
    });

    // Upload handlers
    this.fileDropzone.addEventListener('click', () => this.audioFileInput.click());
    this.audioFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        this.processSelectedFile(e.target.files[0]);
      }
    });
    ['dragenter', 'dragover'].forEach(name => {
      this.fileDropzone.addEventListener(name, (e) => {
        e.preventDefault();
        this.fileDropzone.classList.add('dragover');
      });
    });
    ['dragleave', 'drop'].forEach(name => {
      this.fileDropzone.addEventListener(name, (e) => {
        e.preventDefault();
        this.fileDropzone.classList.remove('dragover');
      });
    });
    this.fileDropzone.addEventListener('drop', (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        this.processSelectedFile(e.dataTransfer.files[0]);
      }
    });
    this.clearUploadBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.clearUploadedFile();
    });

    // Transcribe
    this.transcribeBtn.addEventListener('click', () => this.submitAudioForTranscription());

    // Transcript editor live listeners
    this.transcriptEditor.addEventListener('input', () => {
      this.updateUnclearCounter();
      this.updateWordCount();
    });

    this.startOverBtn.addEventListener('click', () => {
      if (confirm('Are you sure you want to discard this transcript and start over?')) {
        this.resetAll();
      }
    });

    // Extract card (calls /api/extract)
    this.extractCardBtn.addEventListener('click', () => this.submitExtractCard());

    // Back to transcript from review
    this.backToTranscriptBtn.addEventListener('click', () => {
      this.activateSection(3);
      this.sectionTranscript.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    // Expert approval gates the Save button
    this.expertApprovalCheckbox.addEventListener('change', () => {
      this.saveCardBtn.disabled = !this.expertApprovalCheckbox.checked;
    });

    // Save card (calls /api/cards)
    this.saveCardBtn.addEventListener('click', () => this.submitSaveCard());
  }

  // =========================================================================
  // Section 1 — Setup validation
  // =========================================================================
  validateSetupForm() {
    const hasName    = this.expertNameInput.value.trim().length > 0;
    const hasOrigin  = Array.from(this.originRadios).some(r => r.checked);
    const hasConsent = this.consentCheckbox.checked;
    const isValid    = hasName && hasOrigin && hasConsent;
    this.setupContinueBtn.disabled = !isValid;
    return isValid;
  }

  getSelectedOrigin() {
    const selected = Array.from(this.originRadios).find(r => r.checked);
    return selected ? selected.value : 'Real';
  }

  // =========================================================================
  // Section 2 — Capture helpers
  // =========================================================================
  setCaptureMode(mode) {
    if (mode === 'record') {
      this.captureTabRecord.classList.add('active');
      this.captureTabUpload.classList.remove('active');
      this.recordBoxCard.style.display = 'block';
      this.uploadBoxCard.style.display = 'none';
    } else {
      this.captureTabUpload.classList.add('active');
      this.captureTabRecord.classList.remove('active');
      this.recordBoxCard.style.display = 'none';
      this.uploadBoxCard.style.display = 'block';
    }
  }

  async toggleRecording() {
    if (this.audioManager.state === 'recording') {
      this.audioManager.stopRecording();
    } else {
      try {
        this.hideCaptureError();
        await this.audioManager.startRecording();
      } catch (err) {
        this.showCaptureError(err.message);
      }
    }
  }

  updateTimerDisplay(formattedTime) {
    this.recordTimer.textContent = formattedTime;
  }

  handleAudioStateChange(state, data) {
    if (state === 'recording') {
      this.recordBtn.classList.add('recording');
      this.recordStatusText.textContent = 'Recording live audio... Click to stop';
      this.recordPreviewBox.style.display = 'none';
      this.transcribeBtn.disabled = true;
    } else if (state === 'stopped') {
      this.recordBtn.classList.remove('recording');
      this.recordStatusText.textContent = 'Recording stopped. Review playback or re-record:';
      if (data && data.url) {
        this.currentAudioPayload = data;
        if (this.captureTabRecord.classList.contains('active')) {
          this.recordAudioPlayer.src = data.url;
          this.recordPreviewBox.style.display = 'flex';
        }
        this.updateTranscribeButtonState();
      }
    } else {
      this.recordBtn.classList.remove('recording');
    }
  }

  processSelectedFile(file) {
    this.hideCaptureError();
    try {
      const res = this.audioManager.handleUploadedFile(file);
      this.currentAudioPayload = {
        file: res.file,
        url: res.url,
        fileName: res.fileName,
        fileSize: res.fileSize,
      };
      this.uploadAudioPlayer.src = res.url;
      this.uploadFileName.textContent = res.fileName;
      this.uploadFileSize.textContent = `${(res.fileSize / (1024 * 1024)).toFixed(2)} MB`;
      this.uploadPreviewBox.style.display = 'flex';
      this.updateTranscribeButtonState();
    } catch (err) {
      this.showCaptureError(err.message);
      this.clearUploadedFile();
    }
  }

  clearUploadedFile() {
    this.audioFileInput.value = '';
    this.uploadPreviewBox.style.display = 'none';
    if (this.uploadAudioPlayer.src) { this.uploadAudioPlayer.src = ''; }
    this.currentAudioPayload = null;
    this.updateTranscribeButtonState();
  }

  updateTranscribeButtonState() {
    this.transcribeBtn.disabled = !this.currentAudioPayload || !this.currentAudioPayload.file;
  }

  showCaptureError(msg) {
    this.captureErrorMsg.textContent = msg;
    this.captureErrorBanner.style.display = 'flex';
  }

  hideCaptureError() {
    this.captureErrorBanner.style.display = 'none';
  }

  // =========================================================================
  // Section 2 → 3: Transcribe API
  // =========================================================================
  async submitAudioForTranscription() {
    if (!this.currentAudioPayload || !this.currentAudioPayload.file) {
      this.showCaptureError('Please record or select an audio file first.');
      return;
    }
    const file = this.currentAudioPayload.file;
    if (file.size > 10 * 1024 * 1024) {
      this.showCaptureError(`File exceeds maximum allowed size of 10 MB (${(file.size / (1024 * 1024)).toFixed(1)} MB).`);
      return;
    }

    this.hideCaptureError();
    this.captureLoading.style.display = 'flex';
    this.transcribeBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', file, file.name);

    try {
      const response = await fetch('/api/transcribe', { method: 'POST', body: formData });
      if (!response.ok) {
        let detail = 'Transcription failed.';
        try { detail = (await response.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }
      const result = await response.json();
      this.transcriptionResult = result;
      this.populateTranscriptSection(result);
      this.activateSection(3);
      this.sectionTranscript.scrollIntoView({ behavior: 'smooth', block: 'start' });
      this.showToast('Audio transcribed successfully!', 'success');
    } catch (err) {
      this.showCaptureError(err.message);
    } finally {
      this.captureLoading.style.display = 'none';
      this.transcribeBtn.disabled = false;
    }
  }

  populateTranscriptSection(result) {
    const transcript = result.transcript || '';
    this.transcriptEditor.value = transcript;

    const audioUrl = result.audio_url || (this.currentAudioPayload && this.currentAudioPayload.url);
    if (audioUrl) { this.transcriptAudioPlayer.src = audioUrl; }

    const provider = result.stt_provider || 'gemini-3.5-flash';
    this.sttProviderBadge.textContent = provider;

    const isGroq = result.fallback || provider.includes('groq') || provider.includes('whisper');
    this.sttFallbackBanner.style.display = isGroq ? 'flex' : 'none';
    this.sttCachedBadge.style.display    = result.cached ? 'inline-flex' : 'none';

    this.updateUnclearCounter();
    this.updateWordCount();
  }

  // =========================================================================
  // Section 3 — Transcript counter
  // =========================================================================
  updateUnclearCounter() {
    const text  = this.transcriptEditor.value;
    const count = (text.match(/\[unclear\]/gi) || []).length;
    this.unclearCountNumber.textContent = count;
    if (count > 0) {
      this.unclearCounter.className  = 'unclear-counter-badge has-unclear';
      this.unclearCounterText.textContent = count === 1 ? '[unclear] word remaining' : '[unclear] words remaining';
    } else {
      this.unclearCounter.className  = 'unclear-counter-badge clean';
      this.unclearCounterText.textContent = '[unclear] words remaining (all resolved)';
    }
  }

  updateWordCount() {
    const text  = this.transcriptEditor.value.trim();
    const words = text ? text.split(/\s+/).length : 0;
    this.wordCountDisplay.textContent = `${words} words`;
  }

  // =========================================================================
  // Section 3 → 4: Extract Card API
  // =========================================================================
  async submitExtractCard() {
    const transcript = this.transcriptEditor.value.trim();
    if (!transcript) {
      this.showToast('Transcript is empty — cannot extract card.', 'error');
      return;
    }

    // Check for unresolved [unclear] tokens
    const unclearCount = (transcript.match(/\[unclear\]/gi) || []).length;
    if (unclearCount > 0) {
      const confirmed = await this.promptUnclearConfirmation(unclearCount);
      if (!confirmed) {
        this.transcriptEditor.focus();
        return;
      }
    }

    // Show Section 4 immediately (in loading state)
    this.activateSection(4);
    this.sectionReview.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Reset review section UI
    this.extractionErrorBanner.style.display    = 'none';
    this.extractionMetaBar.style.display        = 'none';
    this.extractedFieldsContainer.style.display = 'none';
    this.cardApprovalActions.style.display      = 'none';
    this.saveSuccessBanner.style.display        = 'none';
    this.expertApprovalCheckbox.checked         = false;
    this.saveCardBtn.disabled                   = true;
    this.extractionLoading.style.display        = 'flex';

    try {
      const resp = await fetch('/api/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript, provider: 'gemini' }),
      });

      if (!resp.ok) {
        let detail = 'Extraction failed.';
        try { detail = (await resp.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }

      const result = await resp.json();
      this.extractionResult = result;
      this.renderExtractionFields(result);
      this.showToast('Card fields extracted and quote-verified!', 'success');
    } catch (err) {
      this.extractionErrorMsg.textContent  = err.message;
      this.extractionErrorBanner.style.display = 'flex';
    } finally {
      this.extractionLoading.style.display = 'none';
    }
  }

  /**
   * Warn the user that the transcript still contains [unclear] markers,
   * and require explicit confirmation before extracting.
   * Resolves true if confirmed, false if cancelled.
   */
  promptUnclearConfirmation(count) {
    if (!this.unclearConfirmModal || !this.modalConfirmBtn || !this.modalCancelBtn) {
      return Promise.resolve(
        window.confirm(
          `⚠️ Warning: The transcript still contains ${count} [unclear] marker(s).\n\n` +
          `Quotes containing [unclear] are never accepted as verified diagnostic quotes.\n\n` +
          `Do you want to proceed with extraction anyway?`
        )
      );
    }

    return new Promise((resolve) => {
      if (this.modalUnclearCount) {
        this.modalUnclearCount.textContent = count;
      }
      this.unclearConfirmModal.style.display = 'flex';

      const cleanup = () => {
        this.unclearConfirmModal.style.display = 'none';
        this.modalConfirmBtn.removeEventListener('click', onConfirm);
        this.modalCancelBtn.removeEventListener('click', onCancel);
        document.removeEventListener('keydown', onKeyDown);
        this.unclearConfirmModal.removeEventListener('click', onBackdropClick);
      };

      const onConfirm = () => {
        cleanup();
        resolve(true);
      };

      const onCancel = () => {
        cleanup();
        resolve(false);
      };

      const onKeyDown = (e) => {
        if (e.key === 'Escape') {
          onCancel();
        }
      };

      const onBackdropClick = (e) => {
        if (e.target === this.unclearConfirmModal) {
          onCancel();
        }
      };

      this.modalConfirmBtn.addEventListener('click', onConfirm);
      this.modalCancelBtn.addEventListener('click', onCancel);
      document.addEventListener('keydown', onKeyDown);
      this.unclearConfirmModal.addEventListener('click', onBackdropClick);
      this.modalCancelBtn.focus();
    });
  }

  // =========================================================================
  // Section 4 — Render extracted fields
  // =========================================================================
  renderExtractionFields(result) {
    const fields     = result.fields     || {};
    const modelName  = result.model_name || '—';
    const cached     = result.cached     || false;

    // Meta bar
    this.extractionModelBadge.textContent       = modelName;
    this.extractionCachedBadge.style.display    = cached ? 'inline-flex' : 'none';
    this.extractionMetaBar.style.display        = 'flex';

    const FIELD_LABELS = {
      problem_summary: '🔍 Problem Summary',
      possible_causes: '⚙ Possible Causes',
      checks:          '✓ Verification Checks',
      solution_steps:  '🛠 Solution Steps',
      cautions:        '⚠ Cautions & Warnings',
    };

    for (const [fieldName, fieldData] of Object.entries(fields)) {
      const status      = fieldData.status       || 'not_mentioned';
      const displayText = fieldData.display_text || '';
      const summary     = fieldData.summary      || '';

      // Blockquote primary value
      const quoteEl = document.querySelector(`[data-quote="${fieldName}"]`);
      if (quoteEl) {
        quoteEl.textContent = '';
        quoteEl.className   = 'field-quote';

        if (status === 'verified') {
          quoteEl.textContent  = displayText;
          quoteEl.classList.add('field-quote--verified');
          quoteEl.dir          = 'rtl';
          quoteEl.lang         = 'ar';
        } else if (status === 'unverified') {
          quoteEl.textContent  = displayText; // "Could not be verified – please edit"
          quoteEl.classList.add('field-quote--unverified');
          quoteEl.removeAttribute('dir');
          quoteEl.removeAttribute('lang');
        } else {
          // not_mentioned
          quoteEl.textContent  = displayText; // "Not mentioned" or "No caution stated..."
          quoteEl.classList.add('field-quote--not-mentioned');
          quoteEl.removeAttribute('dir');
          quoteEl.removeAttribute('lang');
        }
      }

      // Optional summary (smaller, below)
      const summaryEl = document.querySelector(`[data-summary="${fieldName}"]`);
      if (summaryEl) {
        if (status === 'verified' && summary) {
          summaryEl.textContent = summary;
          summaryEl.style.display = 'block';
        } else {
          summaryEl.textContent   = '';
          summaryEl.style.display = 'none';
        }
      }

      // Status badge
      const badgeEl = document.querySelector(`[data-status-badge="${fieldName}"]`);
      if (badgeEl) {
        badgeEl.className = 'field-status-badge';
        if (status === 'verified') {
          badgeEl.textContent = '✓ Verified';
          badgeEl.classList.add('field-status-badge--verified');
        } else if (status === 'unverified') {
          badgeEl.textContent = '⚠ Unverified';
          badgeEl.classList.add('field-status-badge--unverified');
        } else {
          badgeEl.textContent = '— Not Mentioned';
          badgeEl.classList.add('field-status-badge--not-mentioned');
        }
      }
    }

    // Show the fields and the approval controls
    this.extractedFieldsContainer.style.display = 'block';
    this.cardApprovalActions.style.display      = 'block';
  }

  // =========================================================================
  // Section 4 → Save: POST /api/cards
  // =========================================================================
  async submitSaveCard() {
    if (!this.expertApprovalCheckbox.checked) {
      this.showToast('Please mark "Expert-Approved" before saving.', 'warning');
      return;
    }
    if (!this.transcriptionResult || !this.extractionResult) {
      this.showToast('Extraction result is missing — please extract the card first.', 'error');
      return;
    }

    const fields  = this.extractionResult.fields  || {};
    const tr      = this.transcriptionResult;

    // Build the payload — each field maps to a CardFieldPayload on the backend
    const payload = {
      expert_name:       this.expertNameInput.value.trim(),
      origin_tag:        this.getSelectedOrigin(),
      transcript:        this.transcriptEditor.value.trim(),
      audio_hash:        tr.audio_hash  || '',
      audio_duration:    tr.duration    || 0,
      stt_provider:      tr.stt_provider || '',
      approved_by_expert: true,
      problem_summary:  this._buildFieldPayload(fields.problem_summary),
      possible_causes:  this._buildFieldPayload(fields.possible_causes),
      checks:           this._buildFieldPayload(fields.checks),
      solution_steps:   this._buildFieldPayload(fields.solution_steps),
      cautions:         this._buildFieldPayload(fields.cautions),
    };

    this.saveLoading.style.display  = 'flex';
    this.saveCardBtn.disabled       = true;
    this.saveSuccessBanner.style.display = 'none';

    try {
      const resp = await fetch('/api/cards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        let detail = 'Save failed.';
        try { detail = (await resp.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }

      const data = await resp.json();
      this.saveSuccessMsg.textContent   = `✓ Card saved (${data.id}) — you can now add another card.`;
      this.saveSuccessBanner.style.display = 'flex';
      this.showToast(`Card saved! ID: ${data.id}`, 'success');

      // ── Full reset after 2.5 s so a second card can be submitted cleanly ──
      setTimeout(() => this.resetAll(), 2500);
    } catch (err) {
      this.showToast(`Save failed: ${err.message}`, 'error');
      this.saveCardBtn.disabled = false;
    } finally {
      this.saveLoading.style.display = 'none';
    }
  }

  /** Convert an extracted field dict into the CardFieldPayload shape. */
  _buildFieldPayload(fieldData) {
    if (!fieldData) {
      return { verbatim_quote: null, summary: null, status: 'not_mentioned', stated: false };
    }
    const quote = fieldData.verbatim_quote || null;
    let status = fieldData.status || 'not_mentioned';

    // Defense-in-depth: Never accept [unclear] marker in a verified quote
    if (status === 'verified' && quote && /\[\s*(?:unclear|غير\s*واضح)\s*\]/i.test(quote)) {
      status = 'unverified';
    }

    return {
      verbatim_quote: quote,
      summary:        fieldData.summary        || null,
      status:         status,
      stated:         fieldData.stated         !== false,
    };
  }

  // =========================================================================
  // Section management
  // =========================================================================
  activateSection(sectionNum) {
    const sections = [
      { num: 1, el: this.sectionSetup },
      { num: 2, el: this.sectionCapture },
      { num: 3, el: this.sectionTranscript },
      { num: 4, el: this.sectionReview },
    ];
    sections.forEach(s => {
      if (s.num < sectionNum) {
        s.el.classList.remove('locked', 'active');
        s.el.classList.add('completed');
        this.stepIndicators[s.num].className = 'step-indicator completed';
      } else if (s.num === sectionNum) {
        s.el.classList.remove('locked', 'completed');
        s.el.classList.add('active');
        this.stepIndicators[s.num].className = 'step-indicator active';
      } else {
        s.el.classList.remove('active', 'completed');
        s.el.classList.add('locked');
        this.stepIndicators[s.num].className = 'step-indicator';
      }
    });
  }

  // =========================================================================
  // Full reset (clears ALL per-contribution state)
  // =========================================================================
  resetAll() {
    // Audio manager
    this.audioManager.reset();

    // Clear per-contribution state
    this.currentAudioPayload  = null;
    this.transcriptionResult  = null;
    this.extractionResult     = null;

    // Reset section 2
    this.recordPreviewBox.style.display = 'none';
    this.recordTimer.textContent        = '00:00';
    this.recordStatusText.textContent   = 'Click the red button to begin recording';
    this.recordBtn.classList.remove('recording');
    this.clearUploadedFile();
    this.hideCaptureError();

    // Reset section 3
    this.transcriptEditor.value         = '';
    this.updateUnclearCounter();
    this.updateWordCount();
    this.sttFallbackBanner.style.display = 'none';
    this.sttCachedBadge.style.display    = 'none';

    // Reset section 4
    this.extractionLoading.style.display        = 'none';
    this.extractionErrorBanner.style.display    = 'none';
    this.extractionMetaBar.style.display        = 'none';
    this.extractedFieldsContainer.style.display = 'none';
    this.cardApprovalActions.style.display      = 'none';
    this.saveSuccessBanner.style.display        = 'none';
    this.expertApprovalCheckbox.checked         = false;
    this.saveCardBtn.disabled                   = true;

    // Clear all field quote/summary/badge text
    document.querySelectorAll('[data-quote]').forEach(el => {
      el.textContent = '';
      el.className   = 'field-quote';
    });
    document.querySelectorAll('[data-summary]').forEach(el => {
      el.textContent   = '';
      el.style.display = 'none';
    });
    document.querySelectorAll('[data-status-badge]').forEach(el => {
      el.textContent = '';
      el.className   = 'field-status-badge';
    });

    // Return to Step 1
    this.activateSection(1);
    this.sectionSetup.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // =========================================================================
  // Toast
  // =========================================================================
  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    const icons = { success: '✓', warning: '⚠', error: '✕', info: 'ℹ' };
    toast.innerHTML = `<span style="font-weight:700;">${icons[type] || 'ℹ'}</span> <span>${message}</span>`;
    this.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity   = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition= 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  }
}
