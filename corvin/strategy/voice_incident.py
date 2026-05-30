"""
F12 — Voice Incident Reporter.

Speech-to-text incident creation: SREs can report incidents verbally,
and Corvin transcribes + structures the report into an InvestigationRequest.

Components:
  • Transcription via Azure Cognitive Services Speech SDK
  • LLM extraction: parses free-form speech into structured fields
  • Creates an InvestigationRequest and triggers the pipeline

This extends the existing TTS briefing (apps/api/routes/investigations.py
/briefing/audio endpoint) with the INPUT direction — STT for incident creation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import litellm

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationRequest, TriggerSource

_log = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of speech-to-text transcription."""
    text: str
    confidence: float
    duration_seconds: float
    language: str = "en-AU"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "duration_seconds": self.duration_seconds,
            "language": self.language,
        }


@dataclass
class VoiceIncidentReport:
    """Structured incident report extracted from voice transcription."""
    transcription: TranscriptionResult
    extracted_request: InvestigationRequest | None = None
    extraction_confidence: str = "medium"
    raw_extraction: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcription": self.transcription.to_dict(),
            "extracted_request": self.extracted_request.model_dump() if self.extracted_request else None,
            "extraction_confidence": self.extraction_confidence,
            "raw_extraction": self.raw_extraction,
        }


class VoiceIncidentService:
    """
    Processes voice audio into structured incident reports.

    Pipeline: Audio bytes → Azure Speech STT → LLM extraction → InvestigationRequest
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("models/llm", get_env())

    def _get_model(self) -> str:
        return self._config.get("fallback_model", "azure/gpt-4.1-mini")

    def transcribe(self, audio_bytes: bytes, content_type: str = "audio/wav") -> TranscriptionResult:
        """
        Transcribe audio bytes to text using Azure Speech SDK.

        Args:
            audio_bytes: Raw audio data (WAV or OGG format)
            content_type: MIME type of the audio

        Returns:
            TranscriptionResult with text and confidence score
        """
        import os
        import time

        speech_key = os.environ.get("AZURE_SPEECH_KEY", "")
        speech_region = os.environ.get("AZURE_SPEECH_REGION", "")

        if not speech_key or not speech_region:
            raise RuntimeError("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not configured")

        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError:
            raise RuntimeError("azure-cognitiveservices-speech SDK not installed")

        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.speech_recognition_language = "en-AU"

        # Create push stream for audio input
        stream = speechsdk.audio.PushAudioInputStream()
        audio_config = speechsdk.audio.AudioConfig(stream=stream)

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        t0 = time.perf_counter()
        stream.write(audio_bytes)
        stream.close()

        result = recognizer.recognize_once()
        elapsed = time.perf_counter() - t0

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return TranscriptionResult(
                text=result.text,
                confidence=0.9,  # SDK doesn't expose confidence directly for recognize_once
                duration_seconds=round(elapsed, 2),
            )
        elif result.reason == speechsdk.ResultReason.NoMatch:
            return TranscriptionResult(
                text="",
                confidence=0.0,
                duration_seconds=round(elapsed, 2),
            )
        else:
            raise RuntimeError(f"Speech recognition failed: {result.reason}")

    def extract_incident(self, transcription: TranscriptionResult) -> VoiceIncidentReport:
        """
        Extract structured incident fields from transcribed text using LLM.

        Parses free-form speech like "We have an issue with the member portal,
        it's returning 500 errors on login" into an InvestigationRequest.
        """
        if not transcription.text:
            return VoiceIncidentReport(
                transcription=transcription,
                extraction_confidence="low",
            )

        prompt = f"""You are Corvin, an SRE AI assistant. A team member just reported an incident verbally.
Transcription: "{transcription.text}"

Extract the incident details into this JSON structure:
{{
  "service_name": "The affected service (e.g., member-portal, claims-api, super-calculator)",
  "environment": "prod|staging|dev (default to prod if not mentioned)",
  "alert_summary": "One-line summary of the issue",
  "severity": "critical|high|medium|low",
  "confidence": "high|medium|low (how confident are you in the extraction)"
}}

If the speaker didn't mention a specific service, use "unknown" for service_name.
Keep alert_summary concise but include key symptoms (error codes, behaviors)."""

        try:
            resp = litellm.completion(
                model=self._get_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(resp.choices[0].message.content)

            request = InvestigationRequest(
                service_name=parsed.get("service_name", "unknown"),
                environment=parsed.get("environment", "prod"),
                alert_summary=parsed.get("alert_summary", transcription.text[:200]),
                trigger_source=TriggerSource.MANUAL,
                raw_payload={"voice_transcription": transcription.text},
            )

            return VoiceIncidentReport(
                transcription=transcription,
                extracted_request=request,
                extraction_confidence=parsed.get("confidence", "medium"),
                raw_extraction=parsed,
            )
        except Exception as exc:
            _log.warning("Voice incident extraction failed: %s", exc)
            # Fallback: create a generic request from the raw text
            request = InvestigationRequest(
                service_name="unknown",
                environment="prod",
                alert_summary=transcription.text[:200] if transcription.text else "Voice-reported incident",
                trigger_source=TriggerSource.MANUAL,
                raw_payload={"voice_transcription": transcription.text},
            )
            return VoiceIncidentReport(
                transcription=transcription,
                extracted_request=request,
                extraction_confidence="low",
                raw_extraction={"error": str(exc)},
            )

    def process_audio(self, audio_bytes: bytes, content_type: str = "audio/wav") -> VoiceIncidentReport:
        """
        Full pipeline: audio → transcription → structured incident.

        This is the main entry point for the voice reporting feature.
        """
        transcription = self.transcribe(audio_bytes, content_type)
        return self.extract_incident(transcription)
