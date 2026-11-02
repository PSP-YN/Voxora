import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "native_backend.py"

def run_request(payload):
    return subprocess.run(
        [sys.executable, str(BACKEND)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=20,
    )

def base_request():
    return {
        "language": "English",
        "text": "Hello from Voxora.",
        "transcript": "A short reference transcript.",
        "reference_audio": str(ROOT / "does-not-exist.wav"),
        "save_profile": False,
    }

def test_rejects_unknown_language():
    payload = base_request()
    payload["language"] = "Klingon"
    result = run_request(payload)
    assert result.returncode != 0
    assert "Choose English, Hindi or Kannada" in result.stdout

def test_rejects_empty_generation_text():
    payload = base_request()
    payload["text"] = "   "
    result = run_request(payload)
    assert result.returncode != 0
    assert "Enter the text you want to speak" in result.stdout

def test_rejects_empty_reference_transcript():
    payload = base_request()
    payload["transcript"] = ""
    result = run_request(payload)
    assert result.returncode != 0
    assert "Enter the exact transcript" in result.stdout

def test_rejects_missing_reference_audio():
    result = run_request(base_request())
    assert result.returncode != 0
    assert "selected voice recording cannot be found" in result.stdout
