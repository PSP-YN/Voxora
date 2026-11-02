"""Local, transparent speaker acoustic analysis for Voxora.

These measurements describe audio signal characteristics, not identity or emotion.
Pitch is estimated on short sampled windows to keep hour-long references affordable.
"""
from __future__ import annotations
import json, math, re, time
from pathlib import Path

PROFILE_VERSION = 1


def analyze_audio(path: str | Path, transcript: str = "", pitch_sample_seconds: float = 8.0) -> dict:
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    info = sf.info(str(path))
    sr = info.samplerate
    frame_len = max(1, int(sr * 0.02))
    hop = frame_len
    total_samples = 0
    sum_sq = 0.0
    peak = 0.0
    silent_samples = 0
    clipped_samples = 0
    pause_frames = 0
    all_frames = 0
    active_frames = 0
    frame_rms_values = []
    sampled_pitch = []
    sampled_centroid = []
    sampled_pitch_window_stats = []
    start = time.monotonic()

    # Stream through the entire audio for level, clipping and pause estimates.
    for block in sf.blocks(str(path), blocksize=sr * 10, dtype="float32", always_2d=True):
        if not block.size:
            continue
        mono = block.mean(axis=1)
        absolute = np.abs(mono)
        total_samples += mono.size
        sum_sq += float(np.sum(mono.astype(np.float64) ** 2))
        peak = max(peak, float(absolute.max(initial=0)))
        silent_samples += int(np.count_nonzero(absolute < 0.005))
        clipped_samples += int(np.count_nonzero(absolute >= 0.999))
        n = len(mono) // frame_len
        if n:
            frames = mono[:n * frame_len].reshape(n, frame_len)
            rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
            frame_rms_values.extend(rms.tolist())
            # silence / pauses are estimated at frame level; 20ms frames.
            is_active = rms >= 0.012
            active_frames += int(is_active.sum())
            pause_frames += int((~is_active).sum())
            all_frames += len(rms)

    # Sample pitch at evenly spaced locations rather than processing a full hour
    # with expensive pitch tracking. Pitch values are robust percentiles.
    try:
        import librosa
        with sf.SoundFile(str(path)) as f:
            duration = len(f) / sr
            if duration <= pitch_sample_seconds:
                starts = [0.0]
            else:
                count = min(12, max(2, int(duration // 60) + 2))
                starts = np.linspace(0, max(0, duration - pitch_sample_seconds), count).tolist()
            seen = set()
            for t in starts:
                key = int(t)
                if key in seen: continue
                seen.add(key)
                f.seek(int(t * sr))
                chunk = f.read(int(pitch_sample_seconds * sr), dtype="float32", always_2d=True).mean(axis=1)
                if len(chunk) < sr // 2: continue
                if sr != 16000:
                    chunk = resample_poly(chunk, 16000, sr)
                pitches = librosa.yin(chunk, fmin=65, fmax=450, sr=16000, frame_length=1024, hop_length=256)
                # Exclude low-confidence/unvoiced extremes using energy and range checks.
                pitches = pitches[(pitches >= 65) & (pitches <= 350) & np.isfinite(pitches)]
                if pitches.size:
                    sampled_pitch.extend(pitches.tolist())
                    sampled_pitch_window_stats.append({
                        "median": float(np.median(pitches)),
                        "std": float(np.std(pitches)),
                        "start_median": float(np.median(pitches[:max(1,len(pitches)//4)])),
                        "end_median": float(np.median(pitches[-max(1,len(pitches)//4):])),
                    })
                spec = np.abs(librosa.stft(chunk, n_fft=1024, hop_length=512))
                sampled_centroid.extend(librosa.feature.spectral_centroid(S=spec, sr=16000)[0].tolist())
    except Exception as e:
        pitch_error = f"Pitch estimation unavailable: {type(e).__name__}: {e}"
    else:
        pitch_error = None

    duration = info.duration
    rms = math.sqrt(sum_sq / max(total_samples, 1))
    dB = lambda x: round(20 * math.log10(max(float(x), 1e-9)), 2)
    pitches = np.asarray(sampled_pitch, dtype=float)
    frame_rms = np.asarray(frame_rms_values, dtype=float)
    quiet = frame_rms < 0.012
    pause_durations=[]
    pause_start=None
    for i, is_quiet in enumerate(quiet):
        if is_quiet and pause_start is None: pause_start=i
        elif not is_quiet and pause_start is not None:
            duration_pause=(i-pause_start)*0.02
            if duration_pause >= 0.20: pause_durations.append(duration_pause)
            pause_start=None
    if pause_start is not None:
        duration_pause=(len(quiet)-pause_start)*0.02
        if duration_pause >= 0.20: pause_durations.append(duration_pause)
    words = re.findall(r"\b[\w’'-]+\b", transcript, flags=re.UNICODE)
    active_seconds = max(0.1, active_frames * 0.02)
    wpm = (len(words) / active_seconds * 60) if words else None
    pitch_median = float(np.median(pitches)) if pitches.size else None
    pitch_p05 = float(np.percentile(pitches, 5)) if pitches.size else None
    pitch_p95 = float(np.percentile(pitches, 95)) if pitches.size else None
    pitch_std = float(np.std(pitches)) if pitches.size else None
    pitch_slopes = [x["end_median"]-x["start_median"] for x in sampled_pitch_window_stats]
    rms_median = float(np.median(frame_rms)) if frame_rms.size else 0.0
    rms_p95 = float(np.percentile(frame_rms,95)) if frame_rms.size else 0.0
    return {
        "profile_version": PROFILE_VERSION,
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "file_name": Path(path).name,
        "duration_seconds": round(duration, 2),
        "sample_rate_hz": sr,
        "channels": info.channels,
        "rms_dbfs": dB(rms),
        "peak_dbfs": dB(peak),
        "near_silence_percent": round(100 * silent_samples / max(total_samples, 1), 2),
        "clipped_sample_percent": round(100 * clipped_samples / max(total_samples, 1), 4),
        "pause_frame_percent": round(100 * pause_frames / max(all_frames, 1), 2),
        "pause_count_estimate": len(pause_durations),
        "pause_median_seconds_estimate": round(float(np.median(pause_durations)), 2) if pause_durations else 0.0,
        "pause_mean_seconds_estimate": round(float(np.mean(pause_durations)), 2) if pause_durations else 0.0,
        "pause_longer_than_1s_count": sum(x >= 1.0 for x in pause_durations),
        "active_speech_seconds_estimate": round(active_seconds, 2),
        "speech_rate_wpm_estimate": round(wpm, 1) if wpm is not None else None,
        "pitch_median_hz": round(pitch_median, 1) if pitch_median else None,
        "pitch_p05_hz": round(pitch_p05, 1) if pitch_p05 else None,
        "pitch_p95_hz": round(pitch_p95, 1) if pitch_p95 else None,
        "pitch_range_hz_estimate": round(pitch_p95 - pitch_p05, 1) if pitch_p05 and pitch_p95 else None,
        "pitch_variability_hz_estimate": round(pitch_std, 1) if pitch_std else None,
        "intonation_slope_hz_estimate": round(float(np.median(pitch_slopes)), 1) if pitch_slopes else None,
        "intonation_slope_variability_hz_estimate": round(float(np.std(pitch_slopes)), 1) if len(pitch_slopes)>1 else None,
        "energy_emphasis_ratio_estimate": round(rms_p95 / max(rms_median, 1e-9), 2) if rms_median else None,
        "spectral_centroid_median_hz": round(float(np.median(sampled_centroid)), 1) if sampled_centroid else None,
        "pitch_sample_method": "YIN pitch tracker on up to 12 evenly spaced 8-second windows",
        "limitations": "Signal-level estimates only; pitch/rhythm/emphasis are not semantic emotion or identity measurements.",
        "analysis_seconds": round(time.monotonic() - start, 2),
        "pitch_error": pitch_error,
    }


def save_profile(profile: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def compare_profiles(reference: dict, generated: dict) -> dict:
    """Metric differences, not a fabricated single similarity score."""
    keys = ["speech_rate_wpm_estimate", "pitch_median_hz", "pitch_range_hz_estimate",
            "pitch_variability_hz_estimate", "rms_dbfs", "pause_frame_percent",
            "spectral_centroid_median_hz"]
    result = {}
    for key in keys:
        a, b = reference.get(key), generated.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            result[key] = {"reference": a, "generated": b, "difference": round(b - a, 2)}
        else:
            result[key] = {"reference": a, "generated": b, "difference": None}
    return {"compared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "metrics": result,
            "interpretation": "Differences are acoustic measurements, not a speaker-identity similarity score."}


def parse_script_markup(text: str, base_settings: dict) -> list[dict]:
    """Parse accessible inline controls: [pause:500ms], [speed:0.9], [delivery:formal], [emphasis]...[/emphasis]."""
    pause_re = re.compile(r"\[pause\s*:\s*(\d{1,5})\s*(ms|s)?\s*\]", re.I)
    speed_re = re.compile(r"\[speed\s*:\s*(0?\.\d+|1(?:\.\d+)?)\s*\]", re.I)
    delivery_re = re.compile(r"\[delivery\s*:\s*(natural|professional|formal|conversational|expressive)\s*\]", re.I)
    emphasis_re = re.compile(r"\[emphasis\](.*?)\[/emphasis\]", re.I | re.S)
    base_speed=float(base_settings.get("speed",1.0))
    parts=[]; pos=0; current_speed=base_speed; delivery="natural"
    tokens = re.compile(r"\[pause\s*:\s*\d{1,5}\s*(?:ms|s)?\s*\]|\[speed\s*:\s*(?:0?\.\d+|1(?:\.\d+)?)\s*\]|\[/speed\]|\[delivery\s*:\s*(?:natural|professional|formal|conversational|expressive)\s*\]|\[/delivery\]|\[emphasis\].*?\[/emphasis\]",re.I|re.S)
    def add_text(segment):
        nonlocal current_speed, delivery
        segment=segment.strip()
        if not segment:return
        # Break long prose at sentence boundaries; preserve punctuation in chunks.
        sentences=re.findall(r".*?(?:[.!?।॥]+|$)",segment,re.S)
        for sent in sentences:
            sent=sent.strip()
            if not sent: continue
            emph=bool(emphasis_re.search(sent))
            clean=emphasis_re.sub(lambda m:m.group(1),sent)
            if clean.strip(): parts.append({"type":"text","text":clean,"speed":current_speed,"delivery":delivery,"emphasis":emph})
    for m in tokens.finditer(text):
        add_text(text[pos:m.start()])
        token=m.group(0)
        pm=pause_re.fullmatch(token)
        sm=speed_re.fullmatch(token)
        dm=delivery_re.fullmatch(token)
        if pm:
            value=int(pm.group(1)); unit=(pm.group(2) or "ms").lower()
            ms=value*1000 if unit=="s" else value
            parts.append({"type":"pause","milliseconds":min(10000,ms)})
        elif sm:
            current_speed=max(.70,min(1.30,float(sm.group(1))))
        elif dm:
            delivery=dm.group(1).lower()
            mapping={"natural":1.0,"professional":.96,"formal":.92,"conversational":1.04,"expressive":1.0}
            current_speed=max(.70,min(1.30,mapping[delivery]))
        elif token.lower() == "[/speed]":
            current_speed=base_speed
        elif token.lower() == "[/delivery]":
            delivery="natural"
        elif emphasis_re.fullmatch(token):
            add_text(token)
        pos=m.end()
    add_text(text[pos:])
    return parts
