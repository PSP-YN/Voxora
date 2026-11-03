"""Adapter discovery and selection; add engines here without changing the UI."""
from .f5_tts import F5TTSAdapter

_ADAPTERS = (F5TTSAdapter(),)

def list_adapters():
    return tuple(_ADAPTERS)

def get_adapter(adapter_id: str):
    for adapter in _ADAPTERS:
        if adapter.descriptor.id == adapter_id:
            return adapter
    raise KeyError(f"Unknown model adapter: {adapter_id}")

def adapter_for_language(language: str):
    for adapter in _ADAPTERS:
        if adapter.supports(language):
            return adapter
    raise ValueError(f"No installed model adapter supports {language!r}")
