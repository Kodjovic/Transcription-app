import os
import re
import logging
import httpx
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

COHERE_TRANSCRIBE_ENDPOINT = "https://api.cohere.com/v1/audio/transcriptions"
COHERE_MODEL = "cohere-transcribe-03-2026"


@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str
    speaker: str = ""       # "Intervenant 1", "Intervenant 2"…  (vide = pas de diarisation)
    confidence: float = 1.0


@dataclass
class TranscriptionResult:
    text: str
    segments: List[TranscriptionSegment]
    language: str
    duration: float
    chunk_offset: float = 0.0


class TranscriptionService:
    def __init__(self):
        self.api_key = os.getenv("COHERE_API_KEY")
        if not self.api_key:
            raise EnvironmentError("COHERE_API_KEY not set in .env file")
        self.supported_languages = [
            "fr", "en", "es", "it", "de", "pt", "ja",
            "zh", "ar", "ru", "ko", "nl", "pl", "auto"
        ]

    def _get_audio_duration(self, audio_path: str) -> float:
        try:
            import librosa
            return float(librosa.get_duration(path=audio_path))
        except Exception:
            try:
                import wave
                with wave.open(audio_path, 'r') as wf:
                    return wf.getnframes() / wf.getframerate()
            except Exception:
                return 0.0

    def transcribe_chunk(
        self,
        audio_path: str,
        language: str = "auto",
        chunk_offset: float = 0.0,
    ) -> TranscriptionResult:
        duration = self._get_audio_duration(audio_path)
        # Cohere requires the 'language' field — "auto" is not a valid value
        lang_param = "fr" if language == "auto" else language

        with open(audio_path, "rb") as audio_file:
            content = audio_file.read()

        # Fields MUST come before the file in multipart body (Cohere requirement)
        files = [
            ("model", (None, COHERE_MODEL)),
            ("language", (None, lang_param)),
        ]

        filename = os.path.basename(audio_path)
        files.append(("file", (filename, content, "audio/wav")))

        try:
            response = httpx.post(
                COHERE_TRANSCRIBE_ENDPOINT,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                timeout=httpx.Timeout(connect=10.0, read=480.0, write=120.0, pool=5.0),
            )
        except httpx.TimeoutException:
            raise RuntimeError("timeout")
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error: {e}")

        if response.status_code == 429:
            raise RuntimeError("rate_limit")
        if response.status_code == 401:
            raise RuntimeError("unauthorized")
        if not response.is_success:
            logger.error(f"Cohere error {response.status_code}: {response.text[:500]}")
            raise RuntimeError(f"API error {response.status_code}: {response.text[:300]}")

        payload = response.json()
        text = payload.get("text", "").strip()

        # Cohere returns only text (no timestamps) — estimate segments from sentences
        segments = self._estimate_segments(text, duration, chunk_offset)

        return TranscriptionResult(
            text=text,
            segments=segments,
            language=lang_param or "auto",
            duration=duration,
            chunk_offset=chunk_offset,
        )

    def _estimate_segments(
        self,
        text: str,
        duration: float,
        offset: float,
    ) -> List[TranscriptionSegment]:
        if not text or duration <= 0:
            return []

        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+|(?<=\n)\s*', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [TranscriptionSegment(start=offset, end=offset + duration, text=text)]

        # Distribute duration proportionally by character count
        total_chars = sum(len(s) for s in sentences)
        if total_chars == 0:
            segment_duration = duration / len(sentences)
            char_weights = [segment_duration] * len(sentences)
        else:
            char_weights = [(len(s) / total_chars) * duration for s in sentences]

        segments = []
        current_time = offset
        for sentence, seg_duration in zip(sentences, char_weights):
            seg_duration = max(seg_duration, 0.5)  # minimum 0.5s per segment
            end_time = min(current_time + seg_duration, offset + duration)
            segments.append(TranscriptionSegment(
                start=round(current_time, 3),
                end=round(end_time, 3),
                text=sentence,
            ))
            current_time = end_time

        return segments

    def merge_results(self, results: List[TranscriptionResult]) -> TranscriptionResult:
        if not results:
            return TranscriptionResult(text="", segments=[], language="unknown", duration=0.0)

        merged_text = " ".join(r.text for r in results if r.text).strip()
        merged_segments = []
        for r in results:
            merged_segments.extend(r.segments)
        merged_segments.sort(key=lambda s: s.start)

        total_duration = sum(r.duration for r in results)
        detected_language = results[0].language

        return TranscriptionResult(
            text=merged_text,
            segments=merged_segments,
            language=detected_language,
            duration=total_duration,
        )
