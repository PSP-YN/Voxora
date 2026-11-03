from model_adapters import adapter_for_language, get_adapter, list_adapters


def test_f5_adapter_declares_current_language_and_capability_boundary():
    adapter = get_adapter('f5-tts')
    caps = adapter.descriptor.capabilities
    assert set(caps.languages) == {'English', 'Hindi', 'Kannada'}
    assert caps.voice_cloning is True
    assert caps.voice_design is False
    assert caps.instruction_control is False
    assert caps.reference_audio_max_seconds == 12.0


def test_language_routes_to_adapter_without_loading_weights():
    assert adapter_for_language('English').descriptor.id == 'f5-tts'
    assert adapter_for_language('Hindi').descriptor.id == 'f5-tts'
    assert adapter_for_language('Kannada').descriptor.id == 'f5-tts'


def test_unknown_language_is_rejected_cleanly():
    try:
        adapter_for_language('Klingon')
    except ValueError as exc:
        assert 'No installed model adapter' in str(exc)
    else:
        raise AssertionError('unknown language must not silently select an adapter')
