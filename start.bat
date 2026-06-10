@echo off
setlocal EnableExtensions
title Jarvis Cyber
cd /d "%~dp0"

echo ============================================
echo   Jarvis Cyber - Demarrage
echo ============================================
echo.

set "VENV_DIR=%CD%\.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Creation de l'environnement virtuel .venv...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo ERREUR: impossible de creer l'environnement virtuel.
        echo Verifiez que Python 3.11 ou plus recent est installe.
        pause
        exit /b 1
    )
    echo Environnement virtuel cree.
) else (
    echo Environnement virtuel detecte.
)

echo.
echo Installation / verification des dependances...
"%PYTHON%" -m pip install --disable-pip-version-check -e ".[dev]"
if errorlevel 1 (
    echo.
    echo ERREUR: l'installation des dependances a echoue.
    echo Le message complet est affiche ci-dessus.
    pause
    exit /b 1
)

echo.
echo Verification des modules principaux...
"%PYTHON%" -c "import fastapi, openai, uvicorn, jarvis_cyber; print('Dependances OK.')"
if errorlevel 1 (
    echo.
    echo ERREUR: certains modules Python ne peuvent pas etre importes.
    pause
    exit /b 1
)

if not exist ".env" (
    echo.
    echo Creation de .env depuis .env.example...
    copy /Y ".env.example" ".env" >nul
)

set "OPENAI_READY="
if defined OPENAI_API_KEY set "OPENAI_READY=1"
if not defined OPENAI_READY (
    findstr /R /C:"^OPENAI_API_KEY=..*" ".env" >nul
    if not errorlevel 1 set "OPENAI_READY=1"
)

if not defined OPENAI_READY (
    echo.
    echo ATTENTION: OPENAI_API_KEY est vide dans .env.
    echo Le chat OpenAI, la transcription, la synthese vocale et Realtime
    echo resteront indisponibles tant que cette cle ne sera pas configuree.
    echo.
    echo Editez ce fichier:
    echo   %CD%\.env
    echo.
) else (
    echo Configuration OpenAI detectee: fonctions IA et voix activees.
)

echo.
echo Demarrage de Jarvis Cyber...
echo Interface: http://127.0.0.1:8000
echo Arret: Ctrl+C
echo.

"%PYTHON%" -m uvicorn jarvis_cyber.api.main:app --host 127.0.0.1 --port 8000
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ERREUR: Jarvis Cyber s'est arrete avec le code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
