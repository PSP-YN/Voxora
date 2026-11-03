#!/usr/bin/env python3
"""One-shot local F5-TTS inference worker for the native GTK desktop app."""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import sys, json, shutil, datetime, traceback, subprocess
from speaker_intelligence import analyze_audio, save_profile, compare_profiles, parse_script_markup
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
    """Compatibility shim; model-specific loading lives in model_adapters."""
    from model_adapters import adapter_for_language
    adapter = adapter_for_language(language)
    return adapter.load(language)


def validate_reference_duration(duration):
    if duration < 3 or duration > 3600:
        raise ValueError(f"Reference audio must be between 3 seconds and 1 hour. Current length: {duration:.1f}s.")

def analyze_reference(path, transcript=""):
    return analyze_audio(path, transcript=transcript)



def apply_voice_effects(audio, sample_rate, settings):
    """Apply bounded local DSP controls after neural synthesis."""
    import numpy as np
    from scipy.signal import butter, sosfilt
    x = np.asarray(audio, dtype=np.float32).reshape(-1).copy()
    if not len(x):
        return x
    brightness = float(settings.get("brightness", 0.0))
    warmth = float(settings.get("warmth", 0.0))
    breathiness = float(settings.get("breathiness", 0.0))
    resonance = float(settings.get("resonance", 0.0))
    compression = float(settings.get("compression", 0.0))
    reverb = float(settings.get("reverb", 0.0))
    def filt(kind, cutoff):
        return sosfilt(butter(2, cutoff, btype=kind, fs=sample_rate, output="sos"), x)
    if abs(brightness) > .005:
        x += brightness * .22 * filt("highpass", min(2200, sample_rate * .40))
    if abs(warmth) > .005:
        x += warmth * .20 * filt("lowpass", min(420, sample_rate * .20))
    if abs(resonance) > .005:
        band = sosfilt(butter(2, [900, min(3200, sample_rate * .42)], btype="bandpass",
                              fs=sample_rate, output="sos"), x)
        x += resonance * .18 * band
    if breathiness > .005:
        rng = np.random.default_rng()
        noise = rng.standard_normal(len(x)).astype(np.float32)
        noise = sosfilt(butter(2, min(3500, sample_rate * .40), btype="highpass",
                               fs=sample_rate, output="sos"), noise)
        noise_rms = float(np.sqrt(np.mean(noise * noise)) + 1e-8)
        signal_rms = float(np.sqrt(np.mean(x * x)) + 1e-8)
        x += noise * (signal_rms * .025 * min(1.0, breathiness) / noise_rms)
    if compression > .005:
        drive = 1.0 + 8.0 * min(1.0, compression)
        shaped = np.tanh(x * drive) / np.tanh(drive)
        x = x * (1.0 - compression * .65) + shaped * (compression * .65)
    if reverb > .005:
        tail = max(1, int(sample_rate * .24 * min(1.0, reverb)))
        dry = x
        x = np.pad(dry, (0, tail))
        wet = np.zeros_like(x)
        for delay_seconds, gain in ((.075, .34), (.150, .16), (.225, .08)):
            delay = max(1, int(sample_rate * delay_seconds))
            if len(x) > delay:
                wet[delay:] += x[:-delay] * gain
        x += wet * min(1.0, reverb) * .55
    return np.clip(x, -1.0, 1.0).astype(np.float32)

def main():
    try:
        request = json.loads(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read())
        language = request["language"]
        text = request["text"].strip()
        transcript = request["transcript"].strip()
        ref_audio = Path(request["reference_audio"]).expanduser()
        if language not in ("English", "Hindi", "Kannada"):
            raise ValueError("Choose English, Hindi or Kannada.")
        action = request.get("action", "generate")
        if action == "generate" and not text:
            raise ValueError("Enter the text you want to speak.")
        if action == "generate" and not transcript:
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
        analysis = analyze_reference(ref_audio, transcript)
        if request.get("save_profile") or action == "analyze":
            save_profile(analysis, VOICES / "speaker_profile.json")
            (VOICES / "my_voice_analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        if action == "analyze":
            emit(stage="complete", message="Speaker profile analysis completed.", analysis=analysis,
                 profile_path=str(VOICES / "speaker_profile.json"))
            if normalized and normalized.exists(): normalized.unlink(missing_ok=True)
            return
        settings = request.get("settings", {})
        speed = max(0.70, min(1.30, float(settings.get("speed", 1.0))))
        cfg_strength = max(1.0, min(4.0, float(settings.get("guidance", 2.0))))
        sway = max(-1.0, min(1.0, float(settings.get("variation", -1.0))))
        target_rms = max(0.04, min(0.20, float(settings.get("loudness", 0.10))))
        pitch_shift = max(-6.0, min(6.0, float(settings.get("pitch_shift", 0.0))))
        intonation = max(0.0, min(1.0, float(settings.get("intonation", 0.0))))
        brightness = max(-1.0, min(1.0, float(settings.get("brightness", 0.0))))
        warmth = max(-1.0, min(1.0, float(settings.get("warmth", 0.0))))
        breathiness = max(0.0, min(1.0, float(settings.get("breathiness", 0.0))))
        resonance = max(-1.0, min(1.0, float(settings.get("resonance", 0.0))))
        compression = max(0.0, min(1.0, float(settings.get("compression", 0.0))))
        reverb = max(0.0, min(1.0, float(settings.get("reverb", 0.0))))
        sentence_pause_ms = max(0, min(2000, int(settings.get("sentence_pause_ms", 180))))
        emphasis_strength = max(0.0, min(1.0, float(settings.get("emphasis_strength", 0.5))))
        mood = str(settings.get("mood", "neutral")).lower()
        mood_params = {
            "neutral": (1.00, 2.0, -1.0), "calm": (.92, 2.1, -.6),
            "upbeat": (1.08, 1.8, .3), "confident": (.98, 2.4, -.3),
            "warm": (.98, 1.9, .1), "dramatic": (.96, 2.0, .5),
        }
        mood_speed, mood_cfg, mood_sway = mood_params.get(mood, mood_params["neutral"])
        mood_intensity = max(0.0, min(1.0, float(settings.get("mood_intensity", 0.5))))
        mood_speed = 1.0 + (mood_speed - 1.0) * mood_intensity
        mood_cfg = 2.0 + (mood_cfg - 2.0) * mood_intensity
        mood_sway = -1.0 + (mood_sway + 1.0) * mood_intensity
        nfe_step = max(16, min(64, int(settings.get("nfe_step", 40))))
        if request.get("save_profile"):
            shutil.copy2(ref_audio, VOICES / "my_voice.wav")
            (VOICES / "my_voice.txt").write_text(transcript, encoding="utf-8")
        emit(stage="loading", message=f"Loading the {language} model on this computer…")
        from model_adapters import adapter_for_language
        adapter = adapter_for_language(language)
        model = adapter.load(language)
        out = OUTPUTS / f"voice_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        emit(stage="generating", message="Generating sentence-aware speech locally…")
        import numpy as np
        segments = parse_script_markup(text, settings)
        sr = None
        writer = None
        pending_tail = None
        pre_pause_ms = 0
        fade_len = None
        text_segment_count = sum(1 for x in segments if x["type"] == "text")
        text_index = 0
        try:
            for idx, segment in enumerate(segments, 1):
                if segment["type"] == "pause":
                    if writer is None:
                        pre_pause_ms += segment["milliseconds"]
                    else:
                        if pending_tail is not None:
                            fade = np.linspace(1.0, 0.0, len(pending_tail), dtype=np.float32)
                            writer.write(pending_tail * fade)
                            pending_tail = None
                        writer.write(np.zeros(int(sr * segment["milliseconds"] / 1000), dtype=np.float32))
                    continue
                delivery = segment.get("delivery", "natural")
                delivery_cfg = {"natural": mood_cfg, "professional": 2.2, "formal": 2.3,
                                "conversational": 1.9, "expressive": 1.8}.get(delivery, cfg_strength)
                delivery_cfg = max(1.0, min(4.0, delivery_cfg + (cfg_strength - 2.0)))
                segment_speed = max(.70, min(1.30, float(segment.get("speed", speed)) * mood_speed))
                segment_cfg = min(4.0, delivery_cfg + (emphasis_strength if segment.get("emphasis") else 0.0))
                emit(stage="generating", message=f"Synthesizing sentence {idx}/{len(segments)} ({delivery}{' · emphasis' if segment.get('emphasis') else ''})…")
                wav, seg_sr, _ = adapter.synthesize(model,
                    reference_audio=str(ref_audio), reference_text=transcript,
                    text=segment["text"], settings={"speed": segment_speed,
                    "cfg_strength": segment_cfg, "nfe_step": nfe_step,
                    "sway_sampling_coef": (mood_sway if mood != "neutral" and sway <= -0.95 else sway),
                    "target_rms": target_rms})
                sr = int(seg_sr)
                audio = np.asarray(wav, dtype=np.float32).reshape(-1)
                # Pitch offset changes the generated segment's baseline. Sentence
                # inflection is a punctuation-aware, subtle segment-level contour;
                # it is deliberately separate from baseline pitch.
                punctuation = segment["text"].rstrip()[-1:] if segment["text"].strip() else ""
                inflection_delta = (0.65 if punctuation in ("?", "？") else
                                    0.35 if punctuation in ("!", "！") else
                                    -0.20 if punctuation in (".", "。", "।") else 0.0)
                applied_pitch = pitch_shift + inflection_delta * intonation
                if abs(applied_pitch) > 0.01:
                    import librosa
                    audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=applied_pitch).astype(np.float32)
                audio = apply_voice_effects(audio, sr, {
                    "brightness": brightness, "warmth": warmth,
                    "breathiness": breathiness, "resonance": resonance,
                    "compression": compression, "reverb": reverb})
                if writer is None:
                    writer = sf.SoundFile(str(out), mode="w", samplerate=sr, channels=1, subtype="PCM_16")
                    if pre_pause_ms:
                        writer.write(np.zeros(int(sr * pre_pause_ms / 1000), dtype=np.float32))
                    fade_len = max(1, int(sr * 0.012))
                if pending_tail is not None:
                    overlap = min(len(pending_tail), len(audio), fade_len)
                    if overlap:
                        fade = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
                        writer.write(pending_tail[-overlap:] * (1.0 - fade) + audio[:overlap] * fade)
                        audio = audio[overlap:]
                    pending_tail = None
                if len(audio) > fade_len:
                    writer.write(audio[:-fade_len])
                    pending_tail = audio[-fade_len:].copy()
                else:
                    pending_tail = audio.copy()
                # A configurable natural gap between sentence segments.
                text_index += 1
                if text_index < text_segment_count and sentence_pause_ms:
                    fade = np.linspace(1.0, 0.0, len(pending_tail), dtype=np.float32)
                    writer.write(pending_tail * fade)
                    pending_tail = None
                    writer.write(np.zeros(int(sr * sentence_pause_ms / 1000), dtype=np.float32))
            if writer is None:
                raise ValueError("No speech segments were found in the script.")
            if pending_tail is not None:
                writer.write(pending_tail)
        finally:
            if writer is not None:
                writer.close()
        generated_analysis=analyze_reference(out, text)
        comparison=compare_profiles(analysis, generated_analysis)
        compare_path=out.with_suffix(".comparison.json")
        compare_path.write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding="utf-8")
        emit(stage="complete", message="Your speech is ready.", output=str(out),
             reference_duration=round(duration, 2), reference_analysis=analysis,
             generated_analysis=generated_analysis, comparison=comparison,
             comparison_path=str(compare_path), settings={"speed": speed,
             "guidance": cfg_strength, "variation": sway, "loudness": target_rms,
             "mood": mood, "pitch_shift": pitch_shift, "intonation": intonation,
             "brightness": brightness, "warmth": warmth, "breathiness": breathiness,
             "resonance": resonance, "compression": compression, "reverb": reverb,
             "sentence_pause_ms": sentence_pause_ms, "emphasis_strength": emphasis_strength,
             "mood_intensity": mood_intensity, "nfe_step": nfe_step})
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
