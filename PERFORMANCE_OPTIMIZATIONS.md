# Optimisations de Performance pour la Diarisation
# ===============================================

## Modèles utilisés

### PyAnnote Speaker Diarization
- **Modèle** : `pyannote/speaker-diarization-3.0` (au lieu de 3.1)
- **Raison** : Plus rapide tout en gardant une bonne précision
- **Configuration** : Chunks de 10 secondes pour traitement plus rapide

### Whisper Timestamped
- **Modèle** : `base` (au lieu de `small`)
- **Raison** : Équilibre vitesse/précision optimal pour la diarisation
- **Usage** : Seulement pour les timestamps précis en mode diarisation

## Optimisations implémentées

### 1. Conversion audio intelligente
- Vérification automatique si le fichier est déjà WAV 16kHz mono
- Évite les conversions inutiles pour les fichiers déjà compatibles

### 2. Paramètres adaptatifs
- Pour fichiers courts (< 1 min) : max 3 intervenants
- Pour fichiers longs (> 1h) : max 10 intervenants
- Optimise les ressources selon la complexité attendue

### 3. Parallélisation
- Pour fichiers < 5 minutes : diarisation et transcription en parallèle
- Réduction significative du temps total pour les fichiers courts
- Traitement séquentiel conservé pour les fichiers longs (stabilité)

### 4. Variables d'environnement
```bash
# Modèle PyAnnote (défaut: pyannote/speaker-diarization-3.0)
DIARIZATION_MODEL=pyannote/speaker-diarization-3.0

# Modèle Whisper (défaut: base)
WHISPER_MODEL=base
```

## Performances attendues

### Avant optimisation
- Diarisation + Transcription : ~2-3x durée du fichier
- Modèle lourd, conversion systématique

### Après optimisation
- Fichiers courts (< 5 min) : ~1.5x durée (parallélisation)
- Fichiers moyens (5-60 min) : ~2x durée (modèle optimisé)
- Fichiers longs (> 1h) : ~2.5x durée (paramètres adaptés)

## Configuration recommandée

Pour maximiser les performances :
1. Utiliser des fichiers WAV 16kHz mono quand possible
2. Pour les tests, utiliser des fichiers courts (< 5 min)
3. Le modèle `base` de Whisper est optimal pour la diarisation
4. Le modèle PyAnnote 3.0 offre le meilleur compromis vitesse/précision