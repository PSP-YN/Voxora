# Voxora

**Private, local voice cloning for English, Hindi and Kannada.** Record or import a short voice sample, enter its exact transcript, paste the text you want spoken, and generate a WAV file on your own computer.

Voxora is a native Linux desktop application built with GTK 4 and libadwaita. It does not open a browser, start a localhost web server, require an account, or call a paid inference API.

![Voxora desktop application](assets/screenshot.png)

## Brand assets

The supplied Voxora logo is used in the desktop sidebar and installed application icon.

## Features

- Zero-shot voice cloning from reference recordings between 3 seconds and 1 hour (the F5-TTS model internally selects a clean representative segment of up to about 12 seconds).
- Full-recording audio analysis (duration, sample rate, RMS/peak level, near-silence and clipping estimates), streamed in blocks.
- Delivery presets (Natural, Professional, Formal, Conversational, Expressive) and supported controls for pace, voice adherence, prosody variation and output loudness.
- Long scripts are split into model-sized batches by F5-TTS; there is no arbitrary 1,000-character UI limit. Practical output length remains constrained by RAM, VRAM, disk space and generation time.
- GStreamer preview with real pause/resume from the current playback position.
- English, Hindi and Kannada model options.
- Import WAV, MP3, FLAC, OGG, M4A and AAC reference audio.
- Record directly from the default microphone.
- Save and reuse a default voice profile.
- Generate WAV audio, play it and browse previous exports.
- Offline inference after the selected models are downloaded.
- Automatic CUDA use when a compatible NVIDIA GPU is available; CPU fallback is supported by F5-TTS.

## Supported systems

- Fedora (GNOME recommended)
- Ubuntu and Debian-based desktop distributions
- Arch Linux and derivatives

The current desktop shell uses GTK 4/libadwaita and is Linux-only. Windows and macOS desktop builds are not currently provided. The inference stack itself is Python-based, but a different native UI port would be needed for those platforms.

## Requirements

- Python 3.11 or 3.12 for the inference environment.
- GTK 4, libadwaita, PyGObject and GStreamer base/good plugins for the desktop UI and audio preview.
- FFmpeg and ALSA utilities for audio conversion and microphone recording.
- 8 GB RAM minimum; 16 GB or more recommended.
- NVIDIA GPU with 6 GB VRAM recommended for faster generation. CPU inference works but can be substantially slower.
- Several GB of free disk space for Python dependencies and model weights. Kannada's published checkpoint is especially large.

## Install

Clone the repository:

    git clone https://github.com/PSP-YN/Voxora.git
    cd Voxora
    chmod +x install.sh
    ./install.sh

The installer installs system libraries using your distribution's package manager, creates an isolated Python environment, installs F5-TTS, registers the desktop launcher and offers to download all three language models.

To skip system package installation (only do this if GTK 4, libadwaita, PyGObject, GStreamer, FFmpeg and ALSA utilities are already installed):

    ./install.sh --no-system-deps

To install the Python environment and desktop launcher without downloading model weights:

    SKIP_MODEL_DOWNLOAD=1 ./install.sh

Download models later:

    .venv/bin/python download_models.py

Or download only selected models:

    .venv/bin/python download_models.py --languages English Hindi

Launch from your Applications menu as **Voxora**, or run:

    ./run.sh

## Create speech

1. Open **Voxora**.
2. Choose English, Hindi or Kannada.
3. Import a clean 3-second to 1-hour recording or use **Record**. F5-TTS uses a representative clean segment (up to about 12 seconds) for cloning; the full source is analyzed for audio-level statistics. A clean 5–12 second segment is still a useful starting point.
4. Enter the exact words spoken in that recording. The transcript should be in the same language as the reference sample.
5. Paste the text to generate. The editor has no fixed 1,000-character limit; long scripts are batched by F5-TTS.
6. Select a delivery preset and tune pace, voice adherence, prosody variation and loudness. These map to actual F5-TTS inference parameters.
7. Select **Generate speech**. The first model load may take several minutes; long scripts can take substantially longer.
8. Use **Play preview / Pause preview / Resume preview** to control playback without restarting it. WAV files are stored in the local outputs/ directory.

For best results, record one speaker in a quiet room, keep the microphone at a consistent distance, and avoid music or background speech. A long recording is analyzed in full for measurable signal statistics, but the current F5-TTS preprocessing stage still selects a representative segment of up to about 12 seconds for voice conditioning. It does not learn a complete speaker-diarized prosody profile from an hour of speech. The presets are parameter mappings, not guaranteed acting directions. Independent controls for emotion, exact intonation contours, accent, timbre and phoneme-level inflection require a model that explicitly supports those controls or a separate prosody-conditioning system. Only clone your own voice or a voice you have explicit permission to use.

## Privacy and network use

Voice samples, transcripts and generated audio are stored on the computer. The inference worker enables Hugging Face and Transformers offline mode. The first-time installer downloads model weights from the upstream public repositories listed in MODEL-LICENSES.md; no inference request is sent to a hosted service.

Voxora does not require API keys, paid endpoints or a user account. Model terms are separate from the app licence: notably, the English F5-TTS pretrained weights are CC BY-NC 4.0 (non-commercial). Review MODEL-LICENSES.md before any commercial use.

## Project layout

    native_app.py          GTK 4 / libadwaita desktop UI
    native_backend.py      isolated F5-TTS inference worker
    download_models.py     public model downloader
    install.sh             Linux dependency and desktop integration setup
    run.sh                 launch the native app
    models/                downloaded local model assets (not committed)
    voices/                private reference recordings (not committed)
    outputs/               generated WAV files (not committed)

## Tests

Install development test tools and run backend validation tests:

    .venv/bin/python -m pip install -r requirements-dev.txt
    .venv/bin/python -m pytest -q tests/test_backend_validation.py

Run the full desktop-to-inference smoke test for each language (requires all models to be installed):

    /usr/bin/python3 native_app.py --self-test English
    /usr/bin/python3 native_app.py --self-test Hindi
    /usr/bin/python3 native_app.py --self-test Kannada

These smoke tests use the F5-TTS bundled demo reference audio. They do not establish similarity to your personal voice; that requires a recording you provide.

## Uninstall

    ./uninstall.sh

This removes the desktop launcher and icon only. It intentionally leaves your model downloads, voice profile and generated exports untouched.

## Licence

The Voxora application code is MIT-licensed. Third-party model weights have separate licences and attribution requirements; see MODEL-LICENSES.md.
