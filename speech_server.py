# Speech server for Render deployment
import os
import tempfile

try:
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("Warning: faster-whisper not available, transcription disabled")

def transcribe_audio(audio_path, language="en"):
    if not WHISPER_AVAILABLE:
        return "Transcription service unavailable"
    
    try:
        segments, info = model.transcribe(audio_path, language=language)
        text = " ".join([seg.text for seg in segments])
        return text.strip()
    except Exception as e:
        print(f"Transcription error: {e}")
        return "Transcription failed"