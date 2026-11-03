# Voxora platform support and Qt promotion gate

## Application selection policy

- The Linux Applications-menu entry launches the Qt/PySide application through `./run-qt.sh`.
- `./run.sh` remains available as the GTK4/libadwaita fallback launcher on Linux.
- `run-qt.bat` is a Windows development entry point, not a signed or supported installer.
- The GTK application, its desktop entry and its Linux dependencies are retained. No default launcher or uninstall behavior is changed as part of this migration.

**Qt must not become the default or replace GTK until both gates below are satisfied.**

## Feature parity gate

| Capability | GTK client | Qt client | Promotion requirement |
|---|---|---|---|
| Local generation in English/Hindi/Kannada | Yes | Yes | Regression tests pass |
| Reference audio import | Yes | Yes | All supported formats tested |
| Microphone recording | Linux `arecord` | Qt Multimedia | Device/codec validation per OS |
| Exact transcript entry | Yes | Yes | Same backend validation |
| Script markup insertion | Selection-aware | Selection-aware | Tests cover all markup helpers |
| 16 continuous voice controls | Yes | Yes | Payload mapping parity tests |
| Delivery and mood presets | Yes | Yes | Preset mapping parity tests |
| Speaker acoustic analysis | Yes | Yes | Display and result parity |
| Generated/reference comparison | Yes | Yes | Metric display parity |
| Preview playback, pause/resume | Yes | Yes | Device and state-transition tests |
| Export/copy WAV | Yes | Yes | File integrity tests |
| Export history | Yes | Yes | Open and export existing file |
| Saved voice profile management | Yes | Yes | Existing data preserved |
| Model capability/license display | Yes | Yes | Adapter metadata is authoritative |

A parity row is not considered complete solely because a button exists. Its behavior must be exercised and its result checked.

## Cross-platform validation gate

| Validation | Fedora Linux | Windows 11 | macOS (Apple Silicon) |
|---|---|---|---|
| Qt window and navigation | Tested | Pending | Pending |
| Audio input enumeration and recording | Tested | Pending | Pending |
| WAV playback, pause and export | Tested on Linux | Pending | Pending |
| Python inference dependencies | Tested on Linux | Pending | Pending |
| CPU inference | Pending full matrix | Pending | Pending |
| NVIDIA/CUDA inference | Tested on current Fedora setup only; regression pending | Pending | N/A |
| Model cache and offline operation | Tested on Linux | Pending | Pending |
| Install, upgrade, uninstall without data loss | Pending | Pending | Pending |
| Signed distributable installer | Pending | Pending | Pending |

Do not advertise Windows/macOS production support or publish installers until their rows have reproducible test evidence. CI compilation on Ubuntu is not a substitute for native OS testing.

## Safe promotion procedure

1. Keep GTK launcher and app ID intact while Qt gaps remain.
2. Run automated backend, adapter, UI, and payload-parity tests.
3. Run real microphone and playback tests on each target OS.
4. Test CPU and supported GPU inference, offline model loading, and upgrade/uninstall data preservation.
5. Build signed, reproducible installers and verify clean-machine installation.
6. Only then change the default launcher; keep a documented GTK fallback for at least one release cycle.
