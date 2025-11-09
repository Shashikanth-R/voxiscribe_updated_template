# Minimal speech_server.py using faster-whisper
from faster_whisper import WhisperModel
import tempfile
import subprocess
import os

model = WhisperModel("base", device="cpu", compute_type="int8")

def convert_webm_to_wav(webm_path, wav_path):
    # ffmpeg command to convert webm to wav
    command = [
        'ffmpeg',
        '-y',  # overwrite output file if it exists
        '-i', webm_path,
        wav_path
    ]
    subprocess.run(command, check=True)

def transcribe_audio(audio_path, language="en"):
    segments, info = model.transcribe(audio_path, language=language)
    text = " ".join([seg.text for seg in segments])
    return text.strip()