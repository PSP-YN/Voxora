#!/usr/bin/env python3
"""One-shot local F5-TTS inference worker for the native GTK desktop app."""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import sys, json, shutil, datetime, traceback, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
OUTPUTS = ROOT / "outputs"
VOICES = ROOT / "voices"
OUTPUTS.mkdir(exist_ok=True)
VOICES.mkdir(exist_ok=True)

def emit(**payload):
    print(json.dumps(payload, ensure_ascii=False), flush=True)

def load_model(language):
    import torch
    from f5_tts.api import F5TTS
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if language == "English":
        return F5TTS(model="F5TTS_v1_Base", device=device)
    if language == "Hindi":
        return F5TTS(model="F5TTS_Small",
                     ckpt_file=str(MODELS / "f5_hindi_small.safetensors"),
                     vocab_file=str(MODELS / "f5_hindi_vocab.txt"), device=device)
    if language == "Kannada":
        import shutil as _shutil
        from importlib.resources import files
        config_dir = Path(files("f5_tts").joinpath("api.py")).resolve().parent / "configs"
        custom = config_dir / "F5TTS_OpenBible_Kannada.yaml"
        supplied = MODELS / "F5TTS_OpenBible_Kannada.yaml"
        if not custom.exists() or custom.read_bytes() != supplied.read_bytes():
            _shutil.copy2(supplied, custom)
        checkpoint = MODELS / "f5_kannada_ema.safetensors"
        if not checkpoint.exists():
            checkpoint = MODELS / "f5_kannada_model_last.pt"
        if not checkpoint.exists():
            raise FileNotFoundError("Kannada model is missing. Run: .venv/bin/python download_models.py --languages Kannada")
        try:
            return F5TTS(model="F5TTS_OpenBible_Kannada",
                         ckpt_file=str(checkpoint),
                         vocab_file=str(MODELS / "f5_kannada_vocab.txt"), device=device)
        except RuntimeError as exc:
            if device != "cuda" or ("out of memory" not in str(exc).lower() and "cuda" not in str(exc).lower()):
                raise
            torch.cuda.empty_cache()
            return F5TTS(model="F5TTS_OpenBible_Kannada",
                         ckpt_file=str(checkpoint),
                         vocab_file=str(MODELS / "f5_kannada_vocab.txt"), device="cpu")
    raise ValueError("Unsupported language: " + str(language))

def validate_reference_duration(duration):
    if duration < 3 or duration > 3600:
        raise ValueError(f"Reference audio must be between 3 seconds and 1 hour. Current length: {duration:.1f}s.")

def analyze_reference(path):
    """Stream the complete reference file and summarize measurable audio traits."""
    import numpy as np
    import soundfile as sf
    info = sf.info(str(path))
    total = 0
    sum_sq = 0.0
    peak = 0.0
    silent = 0
    clipped = 0
    for block in sf.blocks(str(path), blocksize=info.samplerate * 10, dtype="float32", always_2d=True):
        if block.size == 0:
            continue
        abs_block = np.abs(block)
        total += block.size
        sum_sq += float(np.sum(np.square(block), dtype=np.float64))
        peak = max(peak, float(abs_block.max()))
        silent += int(np.count_nonzero(abs_block < 0.005))
        clipped += int(np.count_nonzero(abs_block >= 0.999))
    rms = (sum_sq / max(total, 1)) ** 0.5
    db = lambda x: round(20 * __import__("math").log10(max(x, 1e-9)), 2)
    return {
        "duration_seconds": round(info.duration, 2),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "rms_dbfs": db(rms),
        "peak_dbfs": db(peak),
        "near_silence_percent": round(100 * silent / max(total, 1), 2),
        "clipped_sample_percent": round(100 * clipped / max(total, 1), 4),
        "analysis_scope": "entire recording; streamed in 10-second blocks",
    }

def main():
    try:
        request = json.loads(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read())
        language = request["language"]
        text = request["text"].strip()
        transcript = request["transcript"].strip()
        ref_audio = Path(request["reference_audio"]).expanduser()
        if language not in ("English", "Hindi", "Kannada"):
            raise ValueError("Choose English, Hindi or Kannada.")
        if not text:
            raise ValueError("Enter the text you want to speak.")
        if not transcript:
            raise ValueError("Enter the exact transcript of your voice recording.")
        if not ref_audio.is_file():
            raise ValueError("The selected voice recording cannot be found.")
        import soundfile as sf
        # Normalize compressed formats to a mono WAV before model inference.
        normalized = None
        if ref_audio.suffix.lower() != ".wav":
            normalized = OUTPUTS / f".reference_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"
            converted = subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(ref_audio),
                 "-ac", "1", "-ar", "24000", str(normalized)],
                capture_output=True, text=True
            )
            if converted.returncode != 0:
                raise ValueError("Could not decode this recording. Try WAV, FLAC, OGG or MP3. " + converted.stderr[-400:])
            ref_audio = normalized
        duration = sf.info(str(ref_audio)).duration
        validate_reference_duration(duration)
        # The F5-TTS preprocessing pipeline selects a representative clean segment
        # (up to ~12 seconds) from the complete recording. Keep the original file;
        # never silently replace a user's saved voice recording with a clipped copy.
        emit(stage="analyzing", message=f"Analyzing the full {duration / 60:.1f}-minute reference recording…")
        analysis = analyze_reference(ref_audio)
        if request.get("save_profile"):
            (VOICES / "my_voice_analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        settings = request.get("settings", {})
        speed = max(0.70, min(1.30, float(settings.get("speed", 1.0))))
        cfg_strength = max(1.0, min(4.0, float(settings.get("guidance", 2.0))))
        sway = max(-1.0, min(1.0, float(settings.get("variation", -1.0))))
        target_rms = max(0.04, min(0.20, float(settings.get("loudness", 0.10))))
        if request.get("save_profile"):
            shutil.copy2(ref_audio, VOICES / "my_voice.wav")
            (VOICES / "my_voice.txt").write_text(transcript, encoding="utf-8")
        emit(stage="loading", message=f"Loading the {language} model on this computer…")
        model = load_model(language)
        out = OUTPUTS / f"voice_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        emit(stage="generating", message="Generating speech locally. This can take a few minutes…")
        wav, sr, _ = model.infer(ref_file=str(ref_audio), ref_text=transcript,
                                 gen_text=text, file_wave=str(out), remove_silence=False,
                                 speed=speed, cfg_strength=cfg_strength,
                                 sway_sampling_coef=sway, target_rms=target_rms)
        if not out.exists():
            import numpy as np
            sf.write(str(out), np.asarray(wav, dtype=np.float32), int(sr))
        emit(stage="complete", message="Your speech is ready.", output=str(out),
             reference_duration=round(duration, 2), reference_analysis=analysis, settings={"speed": speed,
             "guidance": cfg_strength, "variation": sway, "loudness": target_rms})
        if normalized and normalized.exists():
            normalized.unlink(missing_ok=True)
    except Exception as exc:
        if "normalized" in locals() and normalized and normalized.exists():
            normalized.unlink(missing_ok=True)
        emit(stage="error", message=f"{type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
