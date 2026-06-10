@echo off
title Jarvis Cyber

echo ============================================
echo   Jarvis Cyber - Demarrage
echo ============================================
echo.

:: Creer l'environnement virtuel s'il n'existe pas
if not exist ".venv\Scripts\activate.bat" (
    echo Creation de l'environnement virtuel .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo ERREUR : impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
    echo Environnement virtuel cree.
    echo.
)

:: Activer l'environnement virtuel
echo Activation de l'environnement virtuel...
call .venv\Scripts\activate.bat

:: Verifier si .env existe
if not exist ".env" (
    if exist ".env.example" (
        echo Fichier .env introuvable. Copie de .env.example vers .env...
        copy .env.example .env
        echo Pensez a configurer votre .env avant de continuer.
        echo.
    ) else (
        echo Attention : aucun fichier .env trouve.
    )
)

:: Installer / mettre a jour les dependances
echo Installation / verification des dependances...
python -m pip install --upgrade pip --quiet
if exist "pyproject.toml" (
    python -m pip install -e ".[dev]" --quiet
) else (
    python -m pip install -r requirements.txt --quiet
)
if errorlevel 1 (
    echo ERREUR : l'installation des dependances a echoue.
    pause
    exit /b 1
)
echo Dependances OK.
echo.

echo Demarrage de Jarvis sur http://127.0.0.1:8000
echo Appuyez sur Ctrl+C pour arreter.
echo.

python -m uvicorn jarvis_cyber.api.main:app --host 127.0.0.1 --port 8000

pause
