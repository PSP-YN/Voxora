"""Stable model-adapter contract. UI and orchestration must not depend on a TTS vendor."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ModelCapabilities:
    languages: tuple[str, ...]
    voice_cloning: bool = True
    voice_design: bool = False
    instruction_control: bool = False
    streaming: bool = False
    reference_audio_max_seconds: float | None = None
    controls: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    name: str
    version: str
    license: str
    capabilities: ModelCapabilities
    local_only: bool = True

class ModelAdapter(ABC):
    descriptor: ModelDescriptor

    @abstractmethod
    def supports(self, language: str) -> bool:
        """Return whether this adapter has a configured model for language."""

    @abstractmethod
    def load(self, language: str, *, device: str = "auto") -> Any:
        """Load and return a model-specific inference handle."""

    @abstractmethod
    def synthesize(self, model: Any, *, reference_audio: str, reference_text: str,
                   text: str, settings: dict[str, Any]) -> tuple[Any, int, Any]:
        """Return (waveform, sample_rate, model_metadata)."""

    def health_check(self) -> dict[str, Any]:
        return {"id": self.descriptor.id, "available": True,
                "languages": list(self.descriptor.capabilities.languages)}
