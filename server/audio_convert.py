import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

from server.config import (
    MAX_UPLOAD_BYTES,
    MAX_AUDIO_DURATION_SECONDS,
    AUDIO_DIR
)

def get_ffmpeg_executable() -> str:
    """Return the ffmpeg binary path from imageio_ffmpeg directly."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    raise RuntimeError("ffmpeg binary not found. Please ensure imageio-ffmpeg is installed in requirements.txt")

def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash directly on original bytes."""
    return hashlib.sha256(data).hexdigest()

def get_audio_duration(ffmpeg_exe: str, file_path: Path) -> float:
    """Extract duration in seconds using ffmpeg output parsing."""
    result = subprocess.run(
        [ffmpeg_exe, "-i", str(file_path)],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True
    )
    # Output looks like: Duration: 00:00:48.50, start: ...
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+|\d+)", result.stderr)
    if not match:
        return 0.0
    hours = float(match.group(1))
    minutes = float(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds

def convert_audio_to_ogg(raw_bytes: bytes, original_extension: str = ".webm") -> Tuple[bytes, float, str]:
    """
    Safely validates upload limits, writes raw bytes to a temporary file
    (never using user-provided filename as path), computes SHA-256 on original bytes,
    and runs ffmpeg via subprocess argument list to convert to OGG Opus.
    
    Returns:
        (converted_ogg_bytes, duration_seconds, original_sha256_hash)
    """
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Audio file exceeds maximum size limit of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    ffmpeg_exe = get_ffmpeg_executable()
    original_hash = compute_sha256(raw_bytes)

    # Sanitize extension (default to .tmp or .webm)
    ext = original_extension.lower().strip()
    if not ext.startswith("."):
        ext = f".{ext}"
    if ext not in [".webm", ".ogg", ".wav", ".mp3", ".m4a", ".aac"]:
        ext = ".bin"

    with tempfile.TemporaryDirectory() as tmpdir:
        input_tmp = Path(tmpdir) / f"input{ext}"
        output_tmp = Path(tmpdir) / "output.ogg"

        with open(input_tmp, "wb") as f:
            f.write(raw_bytes)

        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(input_tmp),
            "-c:a", "libopus",
            "-ar", "48000",
            "-ac", "1",
            str(output_tmp)
        ]

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if proc.returncode != 0:
            err_msg = proc.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Audio conversion failed: {err_msg[:400]}")

        duration = get_audio_duration(ffmpeg_exe, output_tmp)
        if duration > MAX_AUDIO_DURATION_SECONDS:
            raise ValueError(
                f"Audio duration ({duration:.1f}s) exceeds maximum allowed limit of {MAX_AUDIO_DURATION_SECONDS:.0f}s (2 minutes)."
            )

        with open(output_tmp, "rb") as f:
            ogg_bytes = f.read()

        return ogg_bytes, duration, original_hash
