/**
 * Voice of Experience (صوت الخبرة) — Audio Recorder & Upload Handler
 * Handles microphone capture via MediaRecorder and file picker validation.
 */

export class AudioCaptureManager {
  constructor(options = {}) {
    this.maxDurationSec = options.maxDurationSec || 120; // 2 minutes max
    this.maxUploadBytes = options.maxUploadBytes || 10 * 1024 * 1024; // 10 MB limit
    this.onTick = options.onTick || (() => {});
    this.onStateChange = options.onStateChange || (() => {});
    this.onMaxDurationReached = options.onMaxDurationReached || (() => {});

    this.mediaRecorder = null;
    this.audioStream = null;
    this.recordedChunks = [];
    this.timerInterval = null;
    this.elapsedSeconds = 0;
    this.state = 'idle'; // 'idle' | 'recording' | 'stopped'
    this.currentAudioBlob = null;
    this.currentAudioUrl = null;
    this.currentAudioFile = null;
  }

  isRecordingSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }

  getSupportedMimeType() {
    const types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/ogg',
      'audio/mp4'
    ];
    for (const t of types) {
      if (MediaRecorder.isTypeSupported(t)) {
        return t;
      }
    }
    return '';
  }

  async startRecording() {
    if (!this.isRecordingSupported()) {
      throw new Error("Audio recording is not supported in this browser. Please use Chrome or modern desktop browser.");
    }

    try {
      this.audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        throw new Error("Microphone permission was denied. Please allow microphone access in your browser settings and try again.");
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        throw new Error("No microphone was detected on your computer. Please connect a microphone or use the upload option.");
      }
      throw new Error(`Microphone access error: ${err.message}`);
    }

    this.recordedChunks = [];
    const mimeType = this.getSupportedMimeType();
    const options = mimeType ? { mimeType } : {};

    try {
      this.mediaRecorder = new MediaRecorder(this.audioStream, options);
    } catch (err) {
      this.mediaRecorder = new MediaRecorder(this.audioStream);
    }

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        this.recordedChunks.push(event.data);
      }
    };

    this.mediaRecorder.onstop = () => {
      const mime = this.mediaRecorder.mimeType || 'audio/webm';
      const extension = mime.includes('ogg') ? '.ogg' : '.webm';
      this.currentAudioBlob = new Blob(this.recordedChunks, { type: mime });
      this.currentAudioUrl = URL.createObjectURL(this.currentAudioBlob);
      this.currentAudioFile = new File([this.currentAudioBlob], `mic_recording${extension}`, { type: mime });

      if (this.audioStream) {
        this.audioStream.getTracks().forEach(track => track.stop());
        this.audioStream = null;
      }

      this.state = 'stopped';
      this.onStateChange(this.state, {
        blob: this.currentAudioBlob,
        url: this.currentAudioUrl,
        file: this.currentAudioFile,
        duration: this.elapsedSeconds
      });
    };

    this.mediaRecorder.start(250); // collect data in 250ms chunks
    this.elapsedSeconds = 0;
    this.state = 'recording';
    this.onStateChange(this.state);

    this.timerInterval = setInterval(() => {
      this.elapsedSeconds++;
      this.onTick(this.elapsedSeconds, this.formatTime(this.elapsedSeconds));

      if (this.elapsedSeconds >= this.maxDurationSec) {
        this.stopRecording();
        this.onMaxDurationReached(this.maxDurationSec);
      }
    }, 1000);
  }

  stopRecording() {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }

    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
  }

  cancelRecording() {
    this.stopRecording();
    this.reset();
  }

  reset() {
    if (this.currentAudioUrl) {
      URL.revokeObjectURL(this.currentAudioUrl);
      this.currentAudioUrl = null;
    }
    this.currentAudioBlob = null;
    this.currentAudioFile = null;
    this.elapsedSeconds = 0;
    this.state = 'idle';
    this.onStateChange(this.state);
  }

  handleUploadedFile(file) {
    if (!file) {
      throw new Error("No file selected.");
    }

    // Size check (10 MB)
    if (file.size > this.maxUploadBytes) {
      const mb = (this.maxUploadBytes / (1024 * 1024)).toFixed(0);
      throw new Error(`File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds maximum allowed limit of ${mb} MB.`);
    }

    if (file.size === 0) {
      throw new Error("The selected file is empty.");
    }

    // Extension check
    const validExts = ['.ogg', '.webm', '.wav', '.mp3', '.m4a'];
    const nameLower = file.name.toLowerCase();
    const hasValidExt = validExts.some(ext => nameLower.endsWith(ext));
    if (!hasValidExt) {
      throw new Error(`Invalid audio format. Supported formats: ${validExts.join(', ')}`);
    }

    this.reset();
    this.currentAudioFile = file;
    this.currentAudioBlob = file;
    this.currentAudioUrl = URL.createObjectURL(file);
    this.state = 'stopped';

    this.onStateChange(this.state, {
      file: this.currentAudioFile,
      blob: this.currentAudioBlob,
      url: this.currentAudioUrl,
      fileName: file.name,
      fileSize: file.size
    });

    return {
      file: this.currentAudioFile,
      url: this.currentAudioUrl,
      fileName: file.name,
      fileSize: file.size
    };
  }

  formatTime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
}
