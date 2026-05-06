"""
youtube_service.py — Téléchargement de l'audio depuis YouTube (et autres plateformes).

Utilise yt-dlp pour extraire uniquement la piste audio.
Nécessite FFmpeg installé sur le système.
"""

import os
import uuid
import logging

logger = logging.getLogger(__name__)


class YouTubeService:
    """Télécharge l'audio d'une URL YouTube (ou Vimeo, Twitter, etc.)."""

    def download_audio(self, url: str, output_dir: str) -> tuple:
        """
        Télécharge l'audio depuis une URL et le convertit en MP3.

        Args:
            url:        URL de la vidéo (YouTube, Vimeo, etc.)
            output_dir: Dossier de destination

        Returns:
            (audio_path, titre, durée_secondes)
        """
        try:
            import yt_dlp
        except ImportError:
            raise RuntimeError(
                "yt-dlp n'est pas installé. "
                "Exécutez : pip install yt-dlp"
            )

        uid = str(uuid.uuid4())
        output_template = os.path.join(output_dir, f"{uid}_yt")
        final_path = output_template + ".mp3"

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            # Contourne le blocage 403 de YouTube en simulant le client Android
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        }

        logger.info(f"Téléchargement audio depuis : {url}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title    = info.get("title", "video")
                duration = float(info.get("duration") or 0)

        except Exception as e:
            msg = str(e)
            if "Video unavailable" in msg or "not available" in msg.lower():
                raise RuntimeError("Vidéo non disponible ou privée.")
            if "Sign in" in msg or "age" in msg.lower():
                raise RuntimeError("Vidéo réservée aux adultes ou nécessitant une connexion.")
            if "copyright" in msg.lower():
                raise RuntimeError("Vidéo bloquée pour des raisons de droits d'auteur.")
            raise RuntimeError(f"Impossible de télécharger la vidéo : {msg}")

        if not os.path.isfile(final_path):
            raise RuntimeError(
                "Le téléchargement a échoué : fichier audio introuvable. "
                "Vérifiez que FFmpeg est installé correctement."
            )

        size_mb = os.path.getsize(final_path) / (1024 * 1024)
        logger.info(f"Audio téléchargé : '{title}' ({size_mb:.1f} Mo, {duration:.0f}s)")

        return final_path, title, duration
