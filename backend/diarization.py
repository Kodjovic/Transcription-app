"""
diarization.py — Identification des interlocuteurs via PyAnnote Audio.

Nécessite :
  - HF_TOKEN dans .env (token HuggingFace)
  - Modèle accepté sur : https://huggingface.co/pyannote/speaker-diarization-3.1
"""

import os
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class DiarizationService:
    """
    Identifie qui parle et quand dans un fichier audio.
    Utilise le modèle pyannote/speaker-diarization-3.1 (chargé à la première requête).
    """

    def __init__(self):
        self.hf_token = os.getenv("HF_TOKEN", "")
        self._pipeline = None

    def is_available(self) -> bool:
        """Vérifie que le token HuggingFace est configuré."""
        return bool(self.hf_token) and not self.hf_token.startswith("hf_xxx")

    def _get_pipeline(self):
        """Charge le modèle PyAnnote à la première utilisation (lazy loading)."""
        if self._pipeline is not None:
            return self._pipeline

        if not self.is_available():
            raise RuntimeError(
                "HF_TOKEN non configuré. "
                "Ajoutez votre token HuggingFace dans le fichier .env. "
                "Obtenez-le sur https://huggingface.co/settings/tokens"
            )

        logger.info("Chargement du modèle PyAnnote (peut prendre 1-2 min au premier démarrage)...")

        try:
            import torch
            from pyannote.audio import Pipeline

            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=self.hf_token,
            )
            # Forcer l'exécution sur CPU
            self._pipeline = self._pipeline.to(torch.device("cpu"))
            logger.info("Modèle PyAnnote chargé avec succès.")

        except Exception as e:
            self._pipeline = None
            raise RuntimeError(
                f"Impossible de charger PyAnnote : {e}. "
                "Vérifiez votre HF_TOKEN et que vous avez accepté les conditions "
                "sur https://huggingface.co/pyannote/speaker-diarization-3.1"
            )

        return self._pipeline

    def diarize(self, audio_path: str) -> List[Tuple[float, float, str]]:
        """
        Effectue la diarisation sur un fichier WAV (16kHz, mono).

        Args:
            audio_path: Chemin vers le fichier audio

        Returns:
            Liste de (début, fin, "Intervenant N") triée par temps
        """
        # Chargement de l'audio via soundfile (évite torchcodec/torchaudio sur Windows)
        try:
            import soundfile as sf
            import torch
            import numpy as np

            data, sample_rate = sf.read(audio_path, dtype='float32', always_2d=False)
            # Convertir en tenseur (channels, time) attendu par PyAnnote
            if data.ndim == 1:
                waveform = torch.from_numpy(data).unsqueeze(0)
            else:
                waveform = torch.from_numpy(data.T)
        except Exception as e:
            raise RuntimeError(f"Impossible de charger l'audio pour la diarisation : {e}")

        pipeline = self._get_pipeline()

        logger.info(f"Diarisation en cours : {os.path.basename(audio_path)}")
        try:
            diarization = pipeline({
                "waveform": waveform,
                "sample_rate": sample_rate,
            })
        except Exception as e:
            raise RuntimeError(f"Erreur lors de la diarisation : {e}")

        # Trouver l'objet Annotation selon la version de PyAnnote
        logger.info(f"Type retourné par pipeline: {type(diarization).__name__}")
        logger.info(f"Attributs disponibles: {[a for a in dir(diarization) if not a.startswith('_')]}")

        if hasattr(diarization, 'itertracks'):
            annotation = diarization
        elif hasattr(diarization, 'speaker_diarization'):
            annotation = diarization.speaker_diarization
        elif hasattr(diarization, 'annotation'):
            annotation = diarization.annotation
        elif hasattr(diarization, 'diarization'):
            annotation = diarization.diarization
        elif hasattr(diarization, 'chart'):
            annotation = diarization.chart
        else:
            attrs = [a for a in dir(diarization) if not a.startswith('_')]
            raise RuntimeError(
                f"Format de sortie PyAnnote non reconnu ({type(diarization).__name__}). "
                f"Attributs disponibles: {attrs}"
            )

        # Extraire les segments bruts (début, fin, SPEAKER_XX)
        raw_segments = [
            (turn.start, turn.end, speaker)
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]

        if not raw_segments:
            return []

        # Renommer SPEAKER_00 → Intervenant 1, SPEAKER_01 → Intervenant 2, etc.
        speaker_map: dict = {}
        counter = 1
        for _, _, speaker in raw_segments:
            if speaker not in speaker_map:
                speaker_map[speaker] = f"Intervenant {counter}"
                counter += 1

        segments = [
            (round(start, 3), round(end, 3), speaker_map[speaker])
            for start, end, speaker in raw_segments
        ]

        logger.info(
            f"Diarisation terminée : {len(segments)} segments, "
            f"{len(speaker_map)} interlocuteur(s) détecté(s)."
        )
        return segments
