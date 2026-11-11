"""Speech capability and worker startup validation tests."""

import importlib.metadata
from types import SimpleNamespace

import pytest

from interview_service.voice import audio
from interview_service.voice.audio import FakeSTTAdapter, FakeTTSAdapter
from interview_service.voice.config import (
    AudioProviderSettings,
    LiveKitSettings,
    VoiceConfigurationError,
)
from interview_service.voice.worker import create_agent_server


def test_fake_audio_is_deterministic_but_cannot_start_real_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOICE_AUDIO_PROVIDER", "fake")
    settings = AudioProviderSettings.from_env()
    settings.validate_language("en")
    settings.validate_language("si")
    livekit = LiveKitSettings("ws://127.0.0.1:7880", "key", "secret", "agent", 300)
    with pytest.raises(VoiceConfigurationError, match="test-only"):
        create_agent_server(livekit, settings)


def test_google_sinhala_requires_explicitly_validated_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOICE_AUDIO_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.delenv("GOOGLE_TTS_VOICE_SI", raising=False)
    settings = AudioProviderSettings.from_env()
    settings.validate_language("en")
    with pytest.raises(VoiceConfigurationError, match="GOOGLE_TTS_VOICE_SI"):
        settings.validate_language("si")


def test_livekit_configuration_rejects_short_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")
    with pytest.raises(VoiceConfigurationError, match="at least 32"):
        LiveKitSettings.from_env()


def test_locked_livekit_sdk_versions_and_imports() -> None:
    assert importlib.metadata.version("livekit-agents") == "1.8.11"
    assert importlib.metadata.version("livekit-api") == "1.2.2"
    assert importlib.metadata.version("livekit-plugins-google") == "1.8.11"


@pytest.mark.anyio
async def test_fake_speech_adapter_errors_are_deterministic() -> None:
    with pytest.raises(RuntimeError, match="fake STT failure"):
        FakeSTTAdapter(fail=True).finalize("audio transcript")
    with pytest.raises(RuntimeError, match="fake TTS failure"):
        await FakeTTSAdapter(fail=True).speak("question")


def _set_inference_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_AUDIO_PROVIDER", "livekit_inference")
    monkeypatch.setenv("LIVEKIT_INFERENCE_API_KEY", "test-cloud-key")
    monkeypatch.setenv("LIVEKIT_INFERENCE_API_SECRET", "test-cloud-secret")


def test_inference_provider_requires_cloud_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOICE_AUDIO_PROVIDER", "livekit_inference")
    monkeypatch.delenv("LIVEKIT_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_INFERENCE_API_SECRET", raising=False)
    with pytest.raises(VoiceConfigurationError, match="LIVEKIT_INFERENCE_API_KEY"):
        AudioProviderSettings.from_env()


@pytest.mark.parametrize(
    ("language", "stt_model", "voice"),
    [
        ("en", "deepgram/nova-3", "Kore"),
        ("si", "cartesia/ink-whisper", "Kore"),
    ],
)
def test_inference_models_construct_with_language_and_voice(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    stt_model: str,
    voice: str,
) -> None:
    _set_inference_env(monkeypatch)
    captured: dict[str, dict[str, object]] = {}

    def stt(**kwargs: object) -> object:
        captured["stt"] = kwargs
        return object()

    def tts(**kwargs: object) -> object:
        captured["tts"] = kwargs
        return object()

    monkeypatch.setattr(
        audio,
        "_inference_module",
        lambda: SimpleNamespace(STT=stt, TTS=tts),
        raising=False,
    )
    settings = AudioProviderSettings.from_env()
    audio.build_livekit_audio(settings, language)

    assert captured["stt"] == {
        "model": stt_model,
        "language": language,
        "api_key": "test-cloud-key",
        "api_secret": "test-cloud-secret",
    }
    assert captured["tts"] == {
        "model": "google/gemini-3.8-flash-lite-tts",
        "voice": voice,
        "language": language,
        "api_key": "test-cloud-key",
        "api_secret": "test-cloud-secret",
    }


def test_inference_rejects_unsupported_model_and_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_inference_env(monkeypatch)
    monkeypatch.setenv("LIVEKIT_INFERENCE_STT_MODEL_SI", "deepgram/nova-3")
    settings = AudioProviderSettings.from_env()
    with pytest.raises(VoiceConfigurationError, match="Unsupported LiveKit Inference"):
        settings.validate_language("si")
    with pytest.raises(VoiceConfigurationError, match="Unsupported interview language"):
        settings.validate_language("fr")


def test_inference_constructor_errors_are_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_inference_env(monkeypatch)

    def rejected(**_kwargs: object) -> object:
        raise ValueError("invalid model")

    monkeypatch.setattr(
        audio,
        "_inference_module",
        lambda: SimpleNamespace(STT=rejected, TTS=rejected),
        raising=False,
    )
    with pytest.raises(RuntimeError, match="rejected configured en speech models"):
        audio.build_livekit_audio(AudioProviderSettings.from_env(), "en")


def test_google_provider_still_builds_existing_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOICE_AUDIO_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    import livekit.plugins.google as google

    calls: list[tuple[str, dict[str, object]]] = []

    def stt(**kwargs: object) -> object:
        calls.append(("stt", kwargs))
        return object()

    def tts(**kwargs: object) -> object:
        calls.append(("tts", kwargs))
        return object()

    monkeypatch.setattr(google, "STT", stt)
    monkeypatch.setattr(google, "TTS", tts)
    settings = AudioProviderSettings.from_env()
    audio.build_livekit_audio(settings, "en")

    assert [name for name, _kwargs in calls] == ["stt", "tts"]
    assert calls[0][1]["model"] == settings.english_stt_model
    assert calls[1][1]["model_name"] == settings.google_tts_model
