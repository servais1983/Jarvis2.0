@echo off
setlocal EnableExtensions
title J.A.R.V.I.S.
cd /d "%~dp0"

echo ============================================
echo   J.A.R.V.I.S. - Demarrage complet
echo ============================================
echo.

set "VENV_DIR=%CD%\.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

REM ── 1. Environnement virtuel ────────────────────────────────
if not exist "%PYTHON%" (
    echo [1/5] Creation de l'environnement virtuel .venv...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo ERREUR: impossible de creer l'environnement virtuel.
        echo Verifiez que Python 3.11 ou plus recent est installe.
        pause
        exit /b 1
    )
) else (
    echo [1/5] Environnement virtuel detecte.
)

REM ── 2. Dependances (serveur + outils MCP) ───────────────────
echo [2/5] Installation / verification des dependances...
"%PYTHON%" -m pip install --disable-pip-version-check -q -e ".[dev,mcp]"
if errorlevel 1 (
    echo.
    echo ERREUR: l'installation des dependances a echoue.
    pause
    exit /b 1
)
"%PYTHON%" -c "import fastapi, uvicorn, jarvis_cyber; print('      Dependances OK.')"
if errorlevel 1 (
    echo ERREUR: certains modules Python ne peuvent pas etre importes.
    pause
    exit /b 1
)

REM ── 3. Fichiers de configuration ────────────────────────────
echo [3/5] Configuration...
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo       .env cree depuis .env.example
    )
)
if not exist "mcp_servers.json" (
    if exist "mcp_servers.json.example" (
        copy /Y "mcp_servers.json.example" "mcp_servers.json" >nul
        echo       mcp_servers.json cree : serveur MCP de demonstration actif.
        echo       Ajoutez-y vos propres serveurs MCP.
    )
)

REM ── 4. Ollama (cerveau local) ───────────────────────────────
echo [4/5] Verification d'Ollama...
curl -s --max-time 2 http://localhost:11434/api/version >nul 2>&1
if not errorlevel 1 (
    echo       Ollama est deja en ligne : agent local actif.
    goto ollama_done
)
where ollama >nul 2>&1
if errorlevel 1 (
    echo       Ollama n'est pas installe : https://ollama.com
    echo       Jarvis fonctionnera avec OpenAI si configure, sinon en mode local.
    goto ollama_done
)
echo       Demarrage d'Ollama en arriere-plan...
start "Ollama" /MIN cmd /c "ollama serve"
timeout /t 3 /nobreak >nul
curl -s --max-time 2 http://localhost:11434/api/version >nul 2>&1
if not errorlevel 1 (
    echo       Ollama demarre : agent local actif.
) else (
    echo       Ollama n'a pas repondu a temps : il finira de demarrer seul.
)
:ollama_done

REM ── 5. Lancement ────────────────────────────────────────────
echo [5/5] Demarrage de J.A.R.V.I.S. ...
echo.
echo    Interface : http://127.0.0.1:8000
echo    Cliquez sur l'orb et parlez. Arret : Ctrl+C
echo.

REM Ouvre le navigateur une fois le serveur pret
start "" /B cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:8000"

"%PYTHON%" -m uvicorn jarvis_cyber.api.main:app --host 127.0.0.1 --port 8000
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ERREUR: Jarvis s'est arrete avec le code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
