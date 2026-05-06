# Transcription Pro

Application web de transcription audio/vidéo avec deux moteurs au choix :

- **Cohere** (cloud) — rapide, via API, sans identification des interlocuteurs
- **Whisper + PyAnnote** (local) — avec diarisation (qui parle quand) et horodatages précis

Supporte les fichiers locaux et les URLs YouTube. Export en DOCX.

## Stack

- **Backend** : FastAPI, Uvicorn, Whisper (timestamped), PyAnnote, Cohere, yt-dlp
- **Frontend** : HTML / CSS / JavaScript vanilla
- **Audio/Vidéo** : ffmpeg, pydub, librosa

## Prérequis

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) installé et accessible dans le `PATH`
- Une clé API [Cohere](https://dashboard.cohere.com/api-keys) (mode cloud)
- Un token [HuggingFace](https://huggingface.co/settings/tokens) + acceptation des conditions de [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) (mode diarisation)

## Installation

```bash
git clone https://github.com/VOTRE_USER/VOTRE_REPO.git
cd VOTRE_REPO
```

Créer un environnement virtuel et installer les dépendances :

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r backend/requirements.txt
```

## Configuration

Copier le template et renseigner vos clés :

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
```

Éditez `.env` :

```
COHERE_API_KEY=votre_cle_cohere
HF_TOKEN=votre_token_huggingface
WHISPER_MODEL=small
MAX_FILE_SIZE_MB=125
TEMP_DIR=./temp
```

## Lancement

**Windows** : double-cliquer sur `start.bat` ou exécuter :

```powershell
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**macOS/Linux** :

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Puis ouvrir : http://localhost:8000/app

## Structure

```
.
├── backend/
│   ├── main.py              # Serveur FastAPI
│   ├── transcriber.py       # Service Cohere
│   ├── whisper_service.py   # Service Whisper local
│   ├── diarization.py       # PyAnnote
│   ├── audio_utils.py
│   ├── video_utils.py
│   ├── youtube_service.py
│   ├── export.py            # Export DOCX
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── .env.example
├── .gitignore
└── start.bat
```

## Licence

Privé / à définir.
