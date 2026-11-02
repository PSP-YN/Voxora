#!/usr/bin/env python3
"""Download public model assets into Voxora's local model directory."""
from __future__ import annotations
import argparse
import os
import shutil
from pathlib import Path
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)

def fetch(repo: str, filename: str, target_name: str | None = None) -> Path:
    print(f"\nDownloading {repo}/{filename}", flush=True)
    cached = Path(hf_hub_download(repo_id=repo, filename=filename))
    if target_name is None:
        target = cached
    else:
        target = MODELS / target_name
        if cached.resolve() != target.resolve():
            target.unlink(missing_ok=True)
            try:
                os.link(cached.resolve(), target)
            except OSError:
                shutil.copy2(cached, target)
    print(f"Ready: {target} ({target.stat().st_size / 1073741824:.2f} GiB)", flush=True)
    return target

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="+", choices=["English", "Hindi", "Kannada"],
                        default=["English", "Hindi", "Kannada"])
    args = parser.parse_args()
    if "English" in args.languages:
        fetch("SWivid/F5-TTS", "F5TTS_v1_Base/model_1250000.safetensors")
        fetch("charactr/vocos-mel-24khz", "config.yaml")
        fetch("charactr/vocos-mel-24khz", "pytorch_model.bin")
    if "Hindi" in args.languages:
        fetch("SPRINGLab/F5-Hindi-24KHz", "model_2500000.safetensors", "f5_hindi_small.safetensors")
        fetch("SPRINGLab/F5-Hindi-24KHz", "vocab.txt", "f5_hindi_vocab.txt")
    if "Kannada" in args.languages:
        fetch("multilingual-tts/F5-TTS-OpenBible-Kannada", "model_last.pt", "f5_kannada_model_last.pt")
        fetch("multilingual-tts/F5-TTS-OpenBible-Kannada", "vocab.txt", "f5_kannada_vocab.txt")
        fetch("multilingual-tts/F5-TTS-OpenBible-Kannada", "F5-TTS_OpenBible_Kannada.yaml",
              "F5TTS_OpenBible_Kannada.yaml")
    print("\nSelected Voxora model assets are downloaded. Inference itself runs offline.", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
