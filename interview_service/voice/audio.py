"""Speech adapter construction, separate from interview-content AI."""

from dataclasses import dataclass, field

from interview_service.voice.config import AudioProviderSettings


def _inference_module():
    from livekit.agents import inference

    return inference


@dataclass
class FakeSTTAdapter:
    """Deterministic test adapter; it never captures audio or calls a provider."""

    finalized_transcripts: list[str] = field(default_factory=list)
    fail: bool = False

    def finalize(self, text: str) -> str:
        if self.fail:
            raise RuntimeError("fake STT failure")
        transcript = text.strip()
        self.finalized_transcripts.append(transcript)
        return transcript


@dataclass
class FakeTTSAdapter:
    """Deterministic speaker used by orchestration tests."""

    spoken: list[str] = field(default_factory=list)
    fail: bool = False

    async def speak(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("fake TTS failure")
        self.spoken.append(text)


def build_livekit_audio(
    settings: AudioProviderSettings, language: str
) -> tuple[object, object]:
    """Build real LiveKit plugin objects after capability validation."""
    settings.validate_language(language)
    if settings.provider == "fake":
        raise RuntimeError("The fake audio provider is test-only")

    if settings.provider == "livekit_inference":
        inference = _inference_module()

        stt_model = (
            settings.inference_english_stt_model
            if language == "en"
            else settings.inference_sinhala_stt_model
        )
        voice = (
            settings.inference_english_tts_voice
            if language == "en"
            else settings.inference_sinhala_tts_voice
        )
        credentials = {
            "api_key": settings.inference_api_key,
            "api_secret": settings.inference_api_secret,
        }
        try:
            return (
                inference.STT(model=stt_model, language=language, **credentials),
                inference.TTS(
                    model=settings.inference_tts_model,
                    voice=voice,
                    language=language,
                    **credentials,
                ),
            )
        except (ValueError, TypeError) as error:
            raise RuntimeError(
                f"LiveKit Inference rejected configured {language} speech models"
            ) from error

    from livekit.plugins import google

    locale = "en-US" if language == "en" else "si-LK"
    stt_model = (
        settings.english_stt_model if language == "en" else settings.sinhala_stt_model
    )
    voice = (
        settings.english_tts_voice if language == "en" else settings.sinhala_tts_voice
    )
    common: dict[str, str] = {}
    if settings.google_credentials_file:
        common["credentials_file"] = settings.google_credentials_file
    stt_options: dict[str, str] = dict(common)
    if settings.google_project:
        stt_options["project"] = settings.google_project
    return (
        google.STT(
            languages=locale,
            model=stt_model,
            location=settings.google_stt_location,
            speech_end_timeout=settings.stt_timeout_seconds,
            **stt_options,
        ),
        google.TTS(
            language=locale,
            voice_name=voice,
            model_name=settings.google_tts_model,
            **common,
        ),
    )
