# Contributing to Voxora

Voxora is a local-first desktop voice studio. Contributions should be reproducible, privacy-preserving and honest about model capabilities.

## Before you start

1. Read README.md, MODEL-LICENSES.md and docs/VOICE_CONTROLS.md.
2. Open an issue before a large feature or model integration.
3. Never upload voice recordings, transcripts, generated audio, checkpoints, API keys, private logs or speaker profiles.
4. Check model-code and model-weight licences separately. Never bundle weights without redistribution permission.
5. Keep inference local by default; network features must be documented and opt-in.

## Development setup

Current supported desktop target: Linux with GTK 4/libadwaita, Python 3.11 or 3.12, PyGObject, GStreamer base/good plugins, FFmpeg and ALSA utilities. 8 GB RAM minimum; 16 GB recommended. NVIDIA GPU with 6 GB VRAM recommended; CPU fallback is slower. Several GB of disk space are needed for dependencies and models.

Install with ./install.sh. On pre-provisioned Linux use ./install.sh --no-system-deps. Skip model downloads with SKIP_MODEL_DOWNLOAD=1 ./install.sh.

## Checks before pull request

    .venv/bin/python -m py_compile native_app.py native_backend.py speaker_intelligence.py
    .venv/bin/python -m pytest -q
    bash -n install.sh run.sh uninstall.sh
    git diff --check

For model changes, run /usr/bin/python3 native_app.py --self-test English, Hindi and Kannada when weights are installed. Describe OS, hardware, model and test results; do not claim compatibility with untested systems.

## Code expectations

- Keep UI, inference worker, model adapters and audio DSP separated.
- Clamp numeric inputs and validate paths/durations.
- Continuous user controls use 0–100 and document actual mappings.
- A control must have a real effect or be labelled unavailable/experimental.
- Test silence, short signals, mono/stereo and sample-rate edge cases.
- Preserve CPU fallback; never assume CUDA.
- Never overwrite user recordings or generated outputs.
- Add tests for DSP and validation changes; keep model features behind capability metadata.

## Pull request checklist

- [ ] Scope and impact are clear.
- [ ] Tests and syntax checks pass.
- [ ] UI works at narrow and large sizes.
- [ ] No secrets, personal recordings or model weights are included.
- [ ] Licences, performance and memory impact are documented.
- [ ] Screenshots attached for visible UI changes.
- [ ] Limitations and untested platforms are stated.

## Future scope / contributor roadmap

### Voice and synthesis
- Model-adapter interface and capability discovery.
- Instruction-controlled speech for style, emotion, prosody and voice design.
- Word/phoneme-level F0 and duration timeline editor.
- Formant-preserving pitch shift and formant controls.
- Calibrated speaker similarity metrics; multi-reference conditioning; reference cleanup; diarization; profile management.
- Breath placement, phoneme stress, pronunciation dictionary, SSML and language-aware text normalization.
- Non-speech expressive events where licensed models support them; batch generation, chapter splitting and subtitle alignment.

### Audio engineering
- Parametric EQ, de-esser, limiter, noise gate, convolution reverb.
- Waveform editor, spectrogram, F0 contour, LUFS/true-peak meter and A/B audition.
- Undoable non-destructive effect chains and preset import/export.

### Platform and distribution
- Port GTK UI to a maintained cross-platform toolkit such as Qt/PySide.
- Build/test Windows and macOS packages, audio capture/playback, GPU acceleration and model paths.
- Provide Linux Flatpak/AppImage and signed Windows/macOS installers.
- Hardware detection, model recommendations, reproducible builds, SBOM and signed checksums.

### Accessibility and quality
- Keyboard-first workflows, screen-reader labels, high contrast and scalable typography.
- Control grouping, reset-to-neutral, tooltips, preset save/load and loudness-matched A/B.
- Evaluation set using consented/licensed voices, audio regression tests and listening protocols.
- Model cards, dataset provenance, consent and translation guidance.

## Platform status

The current UI is GTK 4/libadwaita and supported on Linux. Python inference may be portable, but Windows/macOS desktop apps are not shipped or validated. A real UI port and per-OS audio/device testing are required before native installers can be published.
