import runpy
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
DSP = runpy.run_path(str(ROOT / 'native_backend.py'))['apply_voice_effects']
def test_voice_effects_neutral_is_identity():
    x = 0.1 * np.sin(2 * np.pi * 220 * np.arange(24000, dtype=np.float32) / 24000)
    y = DSP(x, 24000, {})
    assert y.shape == x.shape and np.allclose(y, x)
def test_voice_effects_are_finite_and_bounded():
    x = 0.1 * np.sin(2 * np.pi * 220 * np.arange(24000, dtype=np.float32) / 24000)
    y = DSP(x, 24000, {'brightness':.7,'warmth':-.4,'breathiness':.5,'resonance':.3,'compression':.8,'reverb':.7})
    assert y.shape[0] > x.shape[0]  # Reverb preserves a natural decay tail.
    assert np.isfinite(y).all() and float(np.max(np.abs(y))) <= 1.0
def test_voice_effects_handle_empty_audio():
    assert DSP(np.array([], dtype=np.float32), 24000, {}).size == 0
