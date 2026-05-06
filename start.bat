@echo off
cd /d "%~dp0backend"
echo ================================================
echo   Transcription Pro - Demarrage du serveur
echo ================================================
echo.
echo Interface disponible sur : http://localhost:8000/app
echo API health check        : http://localhost:8000/health
echo.
echo Appuyez sur Ctrl+C pour arreter le serveur.
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
