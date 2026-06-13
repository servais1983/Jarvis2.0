@echo off
setlocal EnableExtensions
title Jarvis - Assistant Vocal
cd /d "%~dp0"

echo ============================================
echo   Jarvis - Assistant Vocal Local
echo ============================================
echo.

set "VENV_DIR=%CD%\.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Creation de l'environnement virtuel .venv...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERREUR: impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
)

echo Installation des dependances vocales...
"%PYTHON%" -m pip install --disable-pip-version-check -e ".[voice]" -q
if errorlevel 1 (
    echo ERREUR: installation des dependances vocales echouee.
    echo Si pyaudio pose probleme, essayez :
    echo   pip install pipwin ^&^& pipwin install pyaudio
    pause
    exit /b 1
)

echo Verification d'Ollama...
curl -s http://localhost:11434 >nul 2>&1
if errorlevel 1 (
    echo.
    echo ATTENTION: Ollama ne semble pas etre lance.
    echo Telechargez Ollama sur https://ollama.com
    echo Puis lancez : ollama pull deepseek-r1
    echo.
    echo Jarvis essaiera quand meme de demarrer.
    echo Il utilisera OpenAI comme fallback si OPENAI_API_KEY est defini.
    echo.
)

if not exist ".env" (
    if exist ".env.example" copy /Y ".env.example" ".env" >nul
)

for /f "tokens=1,2 delims==" %%A in (.env) do (
    if "%%A"=="OPENAI_API_KEY" set "OPENAI_API_KEY=%%B"
    if "%%A"=="OLLAMA_MODEL" set "OLLAMA_MODEL=%%B"
    if "%%A"=="JARVIS_WAKE_WORD" set "JARVIS_WAKE_WORD=%%B"
)

echo.
echo Demarrage de Jarvis Vocal...
echo Dites 'Jarvis' pour activer l'assistant.
echo Appuyez sur Ctrl+C pour quitter.
echo.

"%PYTHON%" jarvis_vocal.py

pause
