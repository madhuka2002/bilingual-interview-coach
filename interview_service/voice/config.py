"""Validated LiveKit and speech-provider configuration."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class VoiceConfigurationError(RuntimeError):
    """Raised before startup when voice configuration is unsafe or incomplete."""


_GEMINI_TTS_VOICES = {
    "Achernar",
    "Achird",
    "Algenib",
    "Algieba",
    "Alnilam",
    "Aoede",
    "Autonoe",
    "Callirrhoe",
    "Charon",
    "Despina",
    "Enceladus",
    "Erinome",
    "Fenrir",
    "Gacrux",
    "Iapetus",
    "Kore",
    "Laomedeia",
    "Leda",
    "Orus",
    "Pulcherrima",
    "Puck",
    "Rasalgethi",
    "Sadachbia",
    "Sadaltager",
    "Schedar",
    "Sulafat",
    "Umbriel",
    "Vindemiatrix",
    "Zephyr",
    "Zubenelgenubi",
}


def _positive_number(name: str, default: str, cast: type[int] | type[float]):
    raw = os.getenv(name, default)
    try:
        value = cast(raw)
    except ValueError as error:
        raise VoiceConfigurationError(f"{name} must be a number") from error
    if value <= 0:
        raise VoiceConfigurationError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True)
class LiveKitSettings:
    url: str
    api_key: str
    api_secret: str
    agent_name: str
    token_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "LiveKitSettings":
        url = os.getenv("LIVEKIT_URL", "").strip()
        api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
        api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
        agent_name = os.getenv("LIVEKIT_AGENT_NAME", "bic-interviewer").strip()
        missing = [
            name
            for name, value in (
                ("LIVEKIT_URL", url),
                ("LIVEKIT_API_KEY", api_key),
                ("LIVEKIT_API_SECRET", api_secret),
                ("LIVEKIT_AGENT_NAME", agent_name),
            )
            if not value
        ]
        if missing:
            raise VoiceConfigurationError(
                f"Missing voice configuration: {', '.join(missing)}"
            )
        if len(api_secret) < 32:
            raise VoiceConfigurationError(
                "LIVEKIT_API_SECRET must contain at least 32 characters"
            )
        if urlparse(url).scheme not in {"ws", "wss"}:
            raise VoiceConfigurationError("LIVEKIT_URL must use ws or wss")
        ttl = _positive_number("LIVEKIT_TOKEN_TTL_SECONDS", "600", int)
        if ttl > 3600:
            raise VoiceConfigurationError(
                "LIVEKIT_TOKEN_TTL_SECONDS must not exceed 3600"
            )
        return cls(url, api_key, api_secret, agent_name, ttl)


@dataclass(frozen=True)
class AudioProviderSettings:
    provider: str
    stt_timeout_seconds: float
    tts_timeout_seconds: float
    google_credentials_file: str | None
    google_project: str | None
    google_stt_location: str
    english_stt_model: str
    sinhala_stt_model: str
    google_tts_model: str
    english_tts_voice: str
    sinhala_tts_voice: str
    inference_api_key: str | None
    inference_api_secret: str | None
    inference_english_stt_model: str
    inference_sinhala_stt_model: str
    inference_tts_model: str
    inference_english_tts_voice: str
    inference_sinhala_tts_voice: str

    @classmethod
    def from_env(cls) -> "AudioProviderSettings":
        provider = os.getenv("VOICE_AUDIO_PROVIDER", "fake").strip().lower()
        if provider not in {"fake", "google", "livekit_inference"}:
            raise VoiceConfigurationError(
                "VOICE_AUDIO_PROVIDER must be 'fake', 'google', or 'livekit_inference'"
            )
        credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or None
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
        if provider == "google" and not credentials_file and not project:
            raise VoiceConfigurationError(
                "Google speech requires GOOGLE_APPLICATION_CREDENTIALS or "
                "GOOGLE_CLOUD_PROJECT with application default credentials"
            )
        if (
            provider == "google"
            and credentials_file
            and not Path(credentials_file).is_file()
        ):
            raise VoiceConfigurationError(
                "GOOGLE_APPLICATION_CREDENTIALS must name a readable file"
            )
        inference_api_key = os.getenv("LIVEKIT_INFERENCE_API_KEY", "").strip() or None
        inference_api_secret = (
            os.getenv("LIVEKIT_INFERENCE_API_SECRET", "").strip() or None
        )
        if provider == "livekit_inference" and (
            not inference_api_key or not inference_api_secret
        ):
            raise VoiceConfigurationError(
                "LiveKit Inference requires LIVEKIT_INFERENCE_API_KEY and "
                "LIVEKIT_INFERENCE_API_SECRET (LiveKit Cloud credentials)"
            )
        return cls(
            provider=provider,
            stt_timeout_seconds=_positive_number(
                "VOICE_STT_TIMEOUT_SECONDS", "10", float
            ),
            tts_timeout_seconds=_positive_number(
                "VOICE_TTS_TIMEOUT_SECONDS", "10", float
            ),
            google_credentials_file=credentials_file,
            google_project=project,
            google_stt_location=os.getenv("GOOGLE_STT_LOCATION", "global").strip(),
            english_stt_model=os.getenv("GOOGLE_STT_MODEL_EN", "latest_long").strip(),
            sinhala_stt_model=os.getenv("GOOGLE_STT_MODEL_SI", "chirp_2").strip(),
            google_tts_model=os.getenv(
                "GOOGLE_TTS_MODEL", "gemini-2.5-flash-tts"
            ).strip(),
            english_tts_voice=os.getenv("GOOGLE_TTS_VOICE_EN", "Kore").strip(),
            sinhala_tts_voice=os.getenv("GOOGLE_TTS_VOICE_SI", "").strip(),
            inference_api_key=inference_api_key,
            inference_api_secret=inference_api_secret,
            inference_english_stt_model=os.getenv(
                "LIVEKIT_INFERENCE_STT_MODEL_EN", "deepgram/nova-3"
            ).strip(),
            inference_sinhala_stt_model=os.getenv(
                "LIVEKIT_INFERENCE_STT_MODEL_SI", "cartesia/ink-whisper"
            ).strip(),
            inference_tts_model=os.getenv(
                "LIVEKIT_INFERENCE_TTS_MODEL", "google/gemini-3.8-flash-lite-tts"
            ).strip(),
            inference_english_tts_voice=os.getenv(
                "LIVEKIT_INFERENCE_TTS_VOICE_EN", "Kore"
            ).strip(),
            inference_sinhala_tts_voice=os.getenv(
                "LIVEKIT_INFERENCE_TTS_VOICE_SI", "Kore"
            ).strip(),
        )

    def validate_language(self, language: str) -> None:
        if language not in {"en", "si"}:
            raise VoiceConfigurationError(f"Unsupported interview language: {language}")
        if self.provider == "fake":
            return
        if self.provider == "livekit_inference":
            stt_model = (
                self.inference_english_stt_model
                if language == "en"
                else self.inference_sinhala_stt_model
            )
            expected_stt = {
                "en": "deepgram/nova-3",
                "si": "cartesia/ink-whisper",
            }[language]
            if stt_model != expected_stt:
                raise VoiceConfigurationError(
                    "Unsupported LiveKit Inference STT model for "
                    f"{language}: {stt_model}"
                )
            if self.inference_tts_model != "google/gemini-3.8-flash-lite-tts":
                raise VoiceConfigurationError(
                    "Unsupported LiveKit Inference TTS model: "
                    f"{self.inference_tts_model}"
                )
            voice = (
                self.inference_english_tts_voice
                if language == "en"
                else self.inference_sinhala_tts_voice
            )
            if not voice:
                raise VoiceConfigurationError(
                    f"LIVEKIT_INFERENCE_TTS_VOICE_{language.upper()} is required"
                )
            if voice not in _GEMINI_TTS_VOICES:
                raise VoiceConfigurationError(
                    f"Unsupported LiveKit Inference Gemini TTS voice: {voice}"
                )
            return
        if language == "si" and not self.sinhala_tts_voice:
            raise VoiceConfigurationError(
                "Sinhala Google speech requires an explicitly validated "
                "GOOGLE_TTS_VOICE_SI voice"
            )
