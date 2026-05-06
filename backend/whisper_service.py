"""
whisper_service.py — Transcription avec horodatages précis via Whisper Timestamped.

Utilisé uniquement en mode diarisation (pour obtenir les timestamps mot par mot).
Le modèle est chargé en mémoire à la première utilisation.
"""

import os
import logging

logger = logging.getLogger(__name__)

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")


class WhisperService:
    """
    Transcription locale avec horodatage précis.
    Utilise whisper-timestamped (basé sur OpenAI Whisper).
    Tailles disponibles : tiny, base, small (recommandé), medium
    """

    def __init__(self):
        self._model = None
        self.model_size = WHISPER_MODEL_SIZE

    def _get_model(self):
        """Charge le modèle Whisper à la première utilisation (lazy loading)."""
        if self._model is not None:
            return self._model

        logger.info(
            f"Chargement du modèle Whisper '{self.model_size}' "
            "(peut prendre quelques instants au premier démarrage)..."
        )
        try:
            import whisper_timestamped as whisper_ts
            self._model = whisper_ts.load_model(self.model_size, device="cpu")
            logger.info(f"Modèle Whisper '{self.model_size}' chargé avec succès.")
        except Exception as e:
            self._model = None
            raise RuntimeError(f"Impossible de charger le modèle Whisper : {e}")

        return self._model

    def transcribe(self, audio_path: str, language: str = "auto") -> list:
        """
        Transcrit un fichier audio avec horodatages précis.

        Args:
            audio_path : chemin vers le fichier audio (WAV recommandé)
            language   : code langue (fr, en, es…) ou "auto" pour détection automatique

        Returns:
            Liste de segments : [{"start": float, "end": float, "text": str}, ...]
        """
        import whisper_timestamped as whisper_ts

        model = self._get_model()

        kwargs: dict = {
            "verbose": False,
            "detect_disfluencies": False,
            "trust_whisper_timestamps": True,
        }

        # Passer la langue uniquement si elle est explicitement choisie
        if language and language not in ("auto", ""):
            kwargs["language"] = language

        logger.info(f"Transcription Whisper : {os.path.basename(audio_path)}")

        try:
            result = whisper_ts.transcribe(model, audio_path, **kwargs)
        except Exception as e:
            raise RuntimeError(f"Erreur Whisper lors de la transcription : {e}")

        # Extraire les segments avec leurs horodatages
        segments = []
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if text:
                segments.append({
                    "start": round(float(seg.get("start", 0)), 3),
                    "end":   round(float(seg.get("end",   0)), 3),
                    "text":  text,
                })

        logger.info(f"Whisper : {len(segments)} segment(s) générés.")
        return segments
