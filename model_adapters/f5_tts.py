"""F5-TTS adapter. Keeps model loading and vendor inference kwargs out of UI code."""
from pathlib import Path
import shutil
from importlib.resources import files
from .base import ModelAdapter, ModelCapabilities, ModelDescriptor

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

class F5TTSAdapter(ModelAdapter):
    descriptor = ModelDescriptor(
        id="f5-tts", name="F5-TTS family", version="1.1.7",
        license="Per-checkpoint; see MODEL-LICENSES.md",
        capabilities=ModelCapabilities(
            languages=("English", "Hindi", "Kannada"), voice_cloning=True,
            voice_design=False, instruction_control=False, streaming=False,
            reference_audio_max_seconds=12.0,
            controls=("speed", "cfg_strength", "nfe_step", "sway_sampling_coef", "target_rms"),
            notes=("Reference conditioning uses a representative segment up to about 12 seconds.",
                  "No native semantic emotion, phoneme timing or voice-design interface.")))

    def supports(self, language: str) -> bool:
        return language in self.descriptor.capabilities.languages

    def load(self, language: str, *, device: str = "auto"):
        if not self.supports(language):
            raise ValueError(f"F5-TTS does not have a configured {language} model")
        import torch
        from f5_tts.api import F5TTS
        target = ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        if language == "English":
            return F5TTS(model="F5TTS_v1_Base", device=target)
        if language == "Hindi":
            return F5TTS(model="F5TTS_Small", ckpt_file=str(MODELS / "f5_hindi_small.safetensors"),
                         vocab_file=str(MODELS / "f5_hindi_vocab.txt"), device=target)
        config_dir = Path(files("f5_tts").joinpath("api.py")).resolve().parent / "configs"
        supplied = MODELS / "F5TTS_OpenBible_Kannada.yaml"
        custom = config_dir / supplied.name
        if not custom.exists() or custom.read_bytes() != supplied.read_bytes():
            shutil.copy2(supplied, custom)
        checkpoint = MODELS / "f5_kannada_ema.safetensors"
        if not checkpoint.exists():
            checkpoint = MODELS / "f5_kannada_model_last.pt"
        if not checkpoint.exists():
            raise FileNotFoundError("Kannada model is missing. Run: .venv/bin/python download_models.py --languages Kannada")
        try:
            return F5TTS(model="F5TTS_OpenBible_Kannada", ckpt_file=str(checkpoint),
                         vocab_file=str(MODELS / "f5_kannada_vocab.txt"), device=target)
        except RuntimeError as exc:
            if target != "cuda" or ("out of memory" not in str(exc).lower() and "cuda" not in str(exc).lower()):
                raise
            torch.cuda.empty_cache()
            return F5TTS(model="F5TTS_OpenBible_Kannada", ckpt_file=str(checkpoint),
                         vocab_file=str(MODELS / "f5_kannada_vocab.txt"), device="cpu")

    def synthesize(self, model, *, reference_audio, reference_text, text, settings):
        wav, sample_rate, metadata = model.infer(
            ref_file=reference_audio, ref_text=reference_text, gen_text=text,
            file_wave=None, remove_silence=False,
            speed=float(settings.get("speed", 1.0)),
            cfg_strength=float(settings.get("cfg_strength", 2.0)),
            nfe_step=int(settings.get("nfe_step", 40)),
            sway_sampling_coef=float(settings.get("sway_sampling_coef", -1.0)),
            target_rms=float(settings.get("target_rms", 0.10)))
        return wav, int(sample_rate), metadata
