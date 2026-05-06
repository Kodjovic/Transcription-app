"""
main.py — Serveur FastAPI.

Deux modes de transcription :
  1. Cohere (diarize=false) : rapide, via API cloud, sans identification des interlocuteurs
  2. Whisper + PyAnnote (diarize=true) : local, avec interlocuteurs et horodatages précis
"""

import os
import uuid
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import List, Tuple

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from transcriber import TranscriptionService, TranscriptionResult, TranscriptionSegment
from audio_utils import AudioProcessor, AUDIO_EXTENSIONS
from video_utils import VideoProcessor, VIDEO_EXTENSIONS
from export import ExportService
from diarization import DiarizationService
from whisper_service import WhisperService
from youtube_service import YouTubeService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
MAX_FILE_SIZE_MB = float(os.getenv("MAX_FILE_SIZE_MB", "25"))
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

# Instanciation des services
transcription_service = TranscriptionService()
audio_processor       = AudioProcessor()
video_processor       = VideoProcessor()
export_service        = ExportService()
diarization_service   = DiarizationService()
whisper_service       = WhisperService()
youtube_service       = YouTubeService()


# ─── Nettoyage périodique des fichiers temporaires ────────────────────────────

async def cleanup_old_temp_files():
    while True:
        await asyncio.sleep(900)  # toutes les 15 minutes
        try:
            now = time.time()
            for fname in os.listdir(TEMP_DIR):
                fpath = os.path.join(TEMP_DIR, fname)
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > 3600:
                    os.remove(fpath)
                    logger.info(f"Nettoyage : {fname}")
        except Exception as e:
            logger.warning(f"Erreur nettoyage temp : {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(TEMP_DIR, exist_ok=True)
    task = asyncio.create_task(cleanup_old_temp_files())
    yield
    task.cancel()


# ─── Application FastAPI ──────────────────────────────────────────────────────

app = FastAPI(
    title="Transcription Pro API",
    description="Transcription audio/vidéo — Cohere + PyAnnote + Whisper",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir le frontend comme fichiers statiques
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def remove_files(paths: list):
    """Supprime les fichiers temporaires après traitement."""
    for p in paths:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass


def find_dominant_speaker(
    seg_start: float,
    seg_end: float,
    diar_segments: List[Tuple[float, float, str]],
) -> str:
    """
    Retourne le locuteur qui parle le plus longtemps durant l'intervalle [seg_start, seg_end].
    """
    overlaps: dict = {}
    for d_start, d_end, speaker in diar_segments:
        overlap = max(0.0, min(seg_end, d_end) - max(seg_start, d_start))
        if overlap > 0:
            overlaps[speaker] = overlaps.get(speaker, 0.0) + overlap

    return max(overlaps, key=overlaps.get) if overlaps else "Intervenant 1"


def build_diarized_result(
    whisper_segments: list,
    diar_segments: List[Tuple[float, float, str]],
    language: str,
    duration: float,
) -> TranscriptionResult:
    """
    Fusionne les segments Whisper (texte + timestamps) avec la diarisation (locuteurs).
    Regroupe les segments consécutifs du même locuteur.
    """
    # 1. Attribuer un locuteur à chaque segment Whisper
    labeled = []
    for seg in whisper_segments:
        speaker = find_dominant_speaker(seg["start"], seg["end"], diar_segments)
        labeled.append({
            "start":   seg["start"],
            "end":     seg["end"],
            "text":    seg["text"].strip(),
            "speaker": speaker,
        })

    # 2. Fusionner les segments consécutifs du même locuteur (pause < 1.5s)
    merged = []
    for seg in labeled:
        if (
            merged
            and merged[-1]["speaker"] == seg["speaker"]
            and seg["start"] - merged[-1]["end"] < 1.5
            and len(merged[-1]["text"]) < 600
        ):
            merged[-1]["end"]   = seg["end"]
            merged[-1]["text"] += " " + seg["text"]
        else:
            merged.append(dict(seg))

    # 3. Construire les objets TranscriptionSegment
    segments = [
        TranscriptionSegment(
            start=s["start"],
            end=s["end"],
            text=s["text"],
            speaker=s["speaker"],
        )
        for s in merged
        if s["text"]
    ]

    # 4. Texte complet formaté
    full_text = "\n".join(
        f"[{_fmt_ts(s.start)}] 🎙️ {s.speaker} : {s.text}"
        for s in segments
    )

    return TranscriptionResult(
        text=full_text,
        segments=segments,
        language=language,
        duration=duration,
    )


def _fmt_ts(seconds: float) -> str:
    """HH:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":               "ok",
        "ffmpeg_available":     VideoProcessor.is_ffmpeg_available(),
        "cohere_configured":    bool(os.getenv("COHERE_API_KEY")),
        "diarization_available": diarization_service.is_available(),
    }


@app.post("/transcribe")
async def transcribe_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str    = Form(default="auto"),
    diarize: str     = Form(default="false"),   # "true" = mode Whisper + PyAnnote
):
    temp_files = []
    use_diarization = diarize.lower() == "true"

    try:
        # ── Validation de l'extension ─────────────────────────────────────
        filename = file.filename or "upload"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"Format non supporté : '{ext}'. "
                       f"Formats acceptés : {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        if language not in transcription_service.supported_languages:
            language = "auto"

        # ── Sauvegarde du fichier uploadé ────────────────────────────────
        save_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{filename}")
        content   = await file.read()

        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB * 4:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux ({file_size_mb:.1f} Mo). "
                       f"Maximum : {MAX_FILE_SIZE_MB * 4:.0f} Mo",
            )

        with open(save_path, "wb") as f:
            f.write(content)
        temp_files.append(save_path)

        audio_path = save_path

        # ── Extraction audio (si vidéo) ──────────────────────────────────
        if ext in VIDEO_EXTENSIONS:
            if not VideoProcessor.is_ffmpeg_available():
                raise HTTPException(
                    status_code=500,
                    detail="FFmpeg n'est pas installé. Impossible de traiter les vidéos.",
                )
            logger.info(f"Extraction audio depuis la vidéo : {filename}")
            audio_path = video_processor.extract_audio(save_path, output_dir=TEMP_DIR)
            temp_files.append(audio_path)

        # ══════════════════════════════════════════════════════════════════
        # MODE 1 — DIARISATION (Whisper + PyAnnote)
        # ══════════════════════════════════════════════════════════════════
        if use_diarization:
            if not diarization_service.is_available():
                raise HTTPException(
                    status_code=400,
                    detail="HF_TOKEN non configuré dans .env. "
                           "La diarisation nécessite un token HuggingFace.",
                )

            # Obtenir la durée audio
            try:
                audio_duration = audio_processor.get_audio_duration(audio_path)
            except Exception:
                audio_duration = 0.0

            logger.info(f"Mode diarisation activé pour : {filename}")

            # Diarisation (PyAnnote) — qui parle quand ?
            diar_segments = diarization_service.diarize(audio_path)

            # Transcription (Whisper Timestamped) — que dit-on et quand ?
            whisper_segments = whisper_service.transcribe(audio_path, language)

            # Fusion : locuteur + horodatage + texte
            merged = build_diarized_result(
                whisper_segments=whisper_segments,
                diar_segments=diar_segments,
                language=language if language != "auto" else "fr",
                duration=audio_duration,
            )

        # ══════════════════════════════════════════════════════════════════
        # MODE 2 — TRANSCRIPTION SIMPLE (Cohere)
        # ══════════════════════════════════════════════════════════════════
        else:
            # Découpage si fichier > 24 Mo
            chunk_paths = audio_processor.split_audio(
                audio_path, max_chunk_mb=24.0, output_dir=TEMP_DIR
            )
            for p in chunk_paths:
                if p != audio_path:
                    temp_files.append(p)

            logger.info(f"Traitement Cohere — {len(chunk_paths)} segment(s) : {filename}")

            results = []
            offset  = 0.0
            for chunk_path in chunk_paths:
                result = transcription_service.transcribe_chunk(
                    chunk_path, language, chunk_offset=offset
                )
                results.append(result)
                offset += result.duration

            merged = transcription_service.merge_results(results)

        # ── Construction de la réponse ────────────────────────────────────
        exports = export_service.generate_export_response(merged, temp_dir=TEMP_DIR)

        speakers = sorted({seg.speaker for seg in merged.segments if seg.speaker})

        segments_out = [
            {
                "index":   i + 1,
                "start":   round(seg.start, 3),
                "end":     round(seg.end, 3),
                "text":    seg.text,
                "speaker": seg.speaker,
            }
            for i, seg in enumerate(merged.segments)
        ]

        return JSONResponse({
            "success":          True,
            "text":             merged.text,
            "language_detected": merged.language,
            "duration_seconds": round(merged.duration, 2),
            "segments":         segments_out,
            "speakers":         speakers,
            "diarized":         use_diarization,
            "exports":          exports,
            "chunks_processed": len(merged.segments),
        })

    except HTTPException:
        raise
    except RuntimeError as e:
        msg = str(e)
        if "rate_limit" in msg:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Limite de débit atteinte. Réessayez dans 60 secondes."},
                headers={"Retry-After": "60"},
            )
        if "unauthorized" in msg.lower():
            raise HTTPException(status_code=500, detail="Clé API invalide. Vérifiez votre COHERE_API_KEY.")
        if "hf_token" in msg.lower() or "huggingface" in msg.lower():
            raise HTTPException(status_code=500, detail=msg)
        raise HTTPException(status_code=502, detail=f"Erreur de service : {msg}")
    except Exception as e:
        logger.error(f"Erreur non gérée : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")
    finally:
        background_tasks.add_task(remove_files, temp_files)


# ─── Transcription depuis URL (YouTube, Vimeo…) ───────────────────────────────

@app.post("/transcribe-url")
async def transcribe_url(
    background_tasks: BackgroundTasks,
    url:      str = Form(...),
    language: str = Form(default="auto"),
    diarize:  str = Form(default="false"),
):
    temp_files = []
    use_diarization = diarize.lower() == "true"

    try:
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="URL invalide. Elle doit commencer par http:// ou https://")

        if not VideoProcessor.is_ffmpeg_available():
            raise HTTPException(
                status_code=500,
                detail="FFmpeg n'est pas installé. Impossible de télécharger l'audio.",
            )

        if language not in transcription_service.supported_languages:
            language = "auto"

        # ── Téléchargement audio ────────────────────────────────────────
        try:
            audio_path, video_title, video_duration = youtube_service.download_audio(url, TEMP_DIR)
            temp_files.append(audio_path)
        except RuntimeError as e:
            raise HTTPException(status_code=422, detail=str(e))

        logger.info(f"Vidéo téléchargée : '{video_title}'")

        # ══════════════════════════════════════════════════════════════
        # MODE 1 — DIARISATION (Whisper + PyAnnote)
        # ══════════════════════════════════════════════════════════════
        if use_diarization:
            if not diarization_service.is_available():
                raise HTTPException(
                    status_code=400,
                    detail="HF_TOKEN non configuré dans .env. La diarisation nécessite un token HuggingFace.",
                )

            try:
                audio_duration = audio_processor.get_audio_duration(audio_path)
            except Exception:
                audio_duration = video_duration

            diar_segments    = diarization_service.diarize(audio_path)
            whisper_segments = whisper_service.transcribe(audio_path, language)
            merged = build_diarized_result(
                whisper_segments=whisper_segments,
                diar_segments=diar_segments,
                language=language if language != "auto" else "fr",
                duration=audio_duration,
            )

        # ══════════════════════════════════════════════════════════════
        # MODE 2 — TRANSCRIPTION SIMPLE (Cohere)
        # ══════════════════════════════════════════════════════════════
        else:
            chunk_paths = audio_processor.split_audio(audio_path, max_chunk_mb=24.0, output_dir=TEMP_DIR)
            for p in chunk_paths:
                if p != audio_path:
                    temp_files.append(p)

            logger.info(f"Traitement Cohere — {len(chunk_paths)} segment(s) : '{video_title}'")

            results = []
            offset  = 0.0
            for chunk_path in chunk_paths:
                result = transcription_service.transcribe_chunk(chunk_path, language, chunk_offset=offset)
                results.append(result)
                offset += result.duration

            merged = transcription_service.merge_results(results)

        # ── Réponse ───────────────────────────────────────────────────
        exports   = export_service.generate_export_response(merged, temp_dir=TEMP_DIR)
        speakers  = sorted({seg.speaker for seg in merged.segments if seg.speaker})

        segments_out = [
            {
                "index":   i + 1,
                "start":   round(seg.start, 3),
                "end":     round(seg.end, 3),
                "text":    seg.text,
                "speaker": seg.speaker,
            }
            for i, seg in enumerate(merged.segments)
        ]

        return JSONResponse({
            "success":           True,
            "text":              merged.text,
            "language_detected": merged.language,
            "duration_seconds":  round(merged.duration, 2),
            "segments":          segments_out,
            "speakers":          speakers,
            "diarized":          use_diarization,
            "exports":           exports,
            "chunks_processed":  len(merged.segments),
            "video_title":       video_title,
        })

    except HTTPException:
        raise
    except RuntimeError as e:
        msg = str(e)
        if "rate_limit" in msg:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Limite de débit atteinte. Réessayez dans 60 secondes."},
                headers={"Retry-After": "60"},
            )
        raise HTTPException(status_code=502, detail=f"Erreur de service : {msg}")
    except Exception as e:
        logger.error(f"Erreur non gérée (URL) : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")
    finally:
        background_tasks.add_task(remove_files, temp_files)


# ─── Export DOCX ──────────────────────────────────────────────────────────────

class DocxRequest(BaseModel):
    text:             str
    language:         str   = "unknown"
    duration_seconds: float = 0.0
    segments:         list  = []


@app.post("/export/docx")
async def export_docx(request: DocxRequest, background_tasks: BackgroundTasks):
    segments = []
    for seg in request.segments:
        segments.append(TranscriptionSegment(
            start   = seg.get("start", 0),
            end     = seg.get("end", 0),
            text    = seg.get("text", ""),
            speaker = seg.get("speaker", ""),
        ))

    result = TranscriptionResult(
        text     = request.text,
        segments = segments,
        language = request.language,
        duration = request.duration_seconds,
    )

    output_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_transcription.docx")
    export_service.to_docx(result, output_path)
    background_tasks.add_task(remove_files, [output_path])

    return FileResponse(
        path       = output_path,
        filename   = "transcription.docx",
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ─── Gestionnaire d'erreurs global ────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erreur globale : {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Erreur interne du serveur"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        # Augmenter la taille max des requêtes HTTP (en octets) : 500 Mo
        limit_concurrency=10,
        timeout_keep_alive=300,
    )
