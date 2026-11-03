# Voxora application architecture

## Runtime layers

- **Desktop presentation:** `native_app.py` (legacy GTK4/libadwaita) and `qt_app/main.py` (Qt Widgets/PySide6). Both are presentation clients; neither should import a model vendor.
- **Orchestration / audio pipeline:** `native_backend.py`. It validates requests, analyzes references, parses script markup, sequences sentence synthesis, applies post-processing DSP, writes WAV output and emits JSON-line progress events.
- **Model adapter contract:** `model_adapters/base.py`. `ModelAdapter` defines support detection, model loading and synthesis. `ModelCapabilities` describes what a model actually supports; unavailable features must not be exposed as if implemented.
- **Adapter registry:** `model_adapters/registry.py`. Selects an adapter based on language or explicit adapter ID. Add a new adapter and register it here; do not add model-specific branches to the UI.
- **Current adapter:** `model_adapters/f5_tts.py`. Contains F5-TTS checkpoint configuration and translates the neutral synthesis request to F5-specific inference arguments.

## Adding a model

1. Implement `ModelAdapter` in a new module.
2. Describe supported languages, cloning/design/streaming/instruction capabilities, reference limits and genuine controls in `ModelDescriptor`.
3. Implement `supports`, `load`, and `synthesize`.
4. Register the adapter in `model_adapters/registry.py`.
5. Add adapter contract tests and model-specific smoke tests; tests that require large weights or GPU should be explicitly marked and run in an appropriate environment.
6. Update `MODEL-LICENSES.md` for code and weights separately. Never bundle weights without redistribution permission.

## Porting rules

- Keep all model inference out of Qt and GTK event loops; use worker threads/processes.
- Keep request/response payloads serializable and UI-neutral.
- Capabilities are descriptive, not a promise that a UI control has been implemented. Add a control only when the adapter or a clearly labelled DSP stage performs it.
- Keep recordings, profiles, model caches and outputs in user data directories in a future installer; never delete them during app upgrades/uninstall by default.
- Keep `./run.sh` as the default GTK launcher. Do not promote Qt until the feature-parity and native cross-platform validation gates in `docs/PLATFORM_SUPPORT.md` are complete.

## Promotion status

The Qt client has focused Studio and Voice controls pages, selection-aware script markup, delivery presets, profile analysis/comparison, export history and model capability display. The GTK client remains the default and fallback. Native Windows/macOS builds, device testing, inference runtime, installer signing and upgrade/uninstall behavior remain unvalidated. See `docs/PLATFORM_SUPPORT.md` for the explicit promotion gate.
