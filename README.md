# Transcription Pro

Application web de transcription audio avec deux moteurs au choix :

- **Cohere** (cloud) — rapide, via API
- **Whisper + PyAnnote** (local) — avec diarisation (qui parle quand) et horodatages précis

Système intégré d'**accès par codes** et de **crédits** : les utilisateurs reçoivent un nombre de crédits, débité à chaque transcription. L'admin gère les comptes via une interface dédiée.

> ⚠️ **Phase de test** : audio uniquement (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.aac`). L'onglet YouTube est désactivé temporairement.

## Stack

- **Backend** : FastAPI, Uvicorn, Whisper (timestamped), PyAnnote, Cohere
- **Frontend** : HTML / CSS / JavaScript vanilla — thème Memphis
- **Audio** : ffmpeg, pydub, librosa
- **Auth** : SQLite + cookies httponly

## Prérequis

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) dans le `PATH`
- Une clé API [Cohere](https://dashboard.cohere.com/api-keys)
- Un token [HuggingFace](https://huggingface.co/settings/tokens) (pour la diarisation) + acceptation des conditions de [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)

## Installation

```bash
git clone https://github.com/Kodjovic/Transcription-app.git
cd Transcription-app

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r backend/requirements.txt
```

## Configuration

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
```

Éditez `.env` avec vos clés et préférences :

```env
COHERE_API_KEY=votre_cle_cohere
HF_TOKEN=votre_token_huggingface
WHISPER_MODEL=small

# Authentification & crédits
ADMIN_CODE=                   # vide = code aléatoire au 1er démarrage
DEFAULT_CREDITS=30            # crédits offerts par nouvel utilisateur
COST_SIMPLE=5                 # coût d'une transcription Cohere
COST_DIARIZE=10               # coût d'une transcription avec diarisation
ADMIN_CONTACT=                # ex. votre email/WhatsApp affiché aux users sans crédits
COOKIE_SECURE=false           # mettre à true en production HTTPS
```

## Lancement

```powershell
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Au **premier démarrage**, le code admin est imprimé dans la console — notez-le.

- Interface utilisateur : http://localhost:8000/app
- Interface admin : http://localhost:8000/app/admin.html

## Workflow

1. **Vous (admin)** vous connectez avec votre code admin
2. Dans l'onglet Admin, vous **créez des codes utilisateurs** (avec un solde de crédits initial)
3. Vous distribuez les codes à vos utilisateurs
4. Chaque transcription débite le coût correspondant au mode choisi
5. Quand un utilisateur n'a plus de crédits, il vous contacte (le `ADMIN_CONTACT` lui est affiché)
6. Vous rechargez ses crédits depuis l'interface admin

## Structure

```
.
├── backend/
│   ├── main.py              # Serveur FastAPI
│   ├── auth.py              # Auth + crédits (SQLite)
│   ├── auth_routes.py       # Routes /auth/*, /admin/*
│   ├── transcriber.py       # Service Cohere
│   ├── whisper_service.py   # Whisper local
│   ├── diarization.py       # PyAnnote
│   ├── audio_utils.py       # Découpage audio
│   ├── video_utils.py       # Extraction audio (vidéo)
│   ├── youtube_service.py   # Téléchargement audio YouTube
│   ├── export.py            # Export DOCX
│   └── requirements.txt
├── frontend/
│   ├── index.html           # Page principale + login
│   ├── admin.html           # Page admin
│   ├── app.js / admin.js
│   ├── style.css            # Thème Memphis
│   └── admin.css
├── .env.example
├── .gitignore
└── start.bat
```

## Déploiement (HTTPS)

Pour un déploiement en production :

1. Mettre `COOKIE_SECURE=true` dans `.env`
2. Configurer `ADMIN_CODE` avec un code fixe (sinon il change si vous perdez `auth.db`)
3. Configurer `ADMIN_CONTACT` (ex. votre numéro WhatsApp)
4. La base `backend/auth.db` doit être **persistée** (volume Docker, disque persistant)

## Licence

Privé.
