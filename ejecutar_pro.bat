@echo off
REM Doble clic para abrir Dra Cami Contractual (versión PRO con Next.js).
REM Requiere Python 3.11+ y Node.js 20+ instalados.

setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "PYEXE=%VENV%\Scripts\python.exe"

REM --- Verificar Python ---
if not exist "%PYEXE%" (
    echo.
    echo ============================================================
    echo  Primera ejecucion: instalando entorno Python (3-5 minutos)
    echo ============================================================
    where py >nul 2>nul
    if errorlevel 1 (
        where python >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] No encuentro Python. Instala Python 3.11+ desde
            echo         https://www.python.org/downloads/  (marca "Add Python to PATH")
            pause
            exit /b 1
        )
        set "PY=python"
    ) else (
        set "PY=py -3"
    )
    %PY% -m venv "%VENV%"
    "%PYEXE%" -m pip install --upgrade --quiet pip setuptools wheel
    "%PYEXE%" -m pip install --quiet -r requirements.txt
    "%PYEXE%" -m pip install --quiet -e .
)

REM --- Verificar Node ---
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No encuentro Node.js. Instala Node 20+ desde
    echo         https://nodejs.org/   (LTS recomendado)
    pause
    exit /b 1
)

set PYTHONPATH=src

REM --- Asegurar pywebview (ventana nativa) ---
"%PYEXE%" -c "import webview" >nul 2>nul
if errorlevel 1 (
    echo Instalando ventana nativa pywebview ^(primera vez, ~30s^)...
    "%PYEXE%" -m pip install --quiet pywebview
)

echo.
echo Abriendo Sistema de Seguimiento Contratos FEAB - Dra Cami...
echo (Se abrira como ventana propia. No cierres esta consola.)
echo.

"%PYEXE%" -m secop_ii.launcher_window

pause
