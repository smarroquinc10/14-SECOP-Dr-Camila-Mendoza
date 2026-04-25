@echo off
REM Doble clic para abrir el Dra Cami Contractual en el navegador.
REM La primera vez crea el entorno virtual y descarga dependencias — puede
REM tardar unos minutos. Las siguientes veces arranca al instante.

setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "PYEXE=%VENV%\Scripts\python.exe"

REM --- 1) Asegurar que el .venv existe -----------------------------------
if not exist "%PYEXE%" (
    echo.
    echo ==========================================================
    echo  Primera ejecucion: creando entorno virtual e instalando
    echo  dependencias. Esto tarda unos minutos la primera vez.
    echo  Las siguientes veces sera instantaneo.
    echo ==========================================================
    echo.

    where py >nul 2>nul
    if errorlevel 1 (
        where python >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] No encuentro Python instalado.
            echo         Instala Python 3.11 o superior desde:
            echo         https://www.python.org/downloads/
            echo.
            echo         Marca la opcion "Add Python to PATH" al instalar.
            echo.
            pause
            exit /b 1
        )
        set "PY=python"
    ) else (
        set "PY=py -3"
    )

    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] No pude crear el entorno virtual.
        pause
        exit /b 1
    )

    "%PYEXE%" -m pip install --upgrade --quiet pip setuptools wheel
    echo Instalando dependencias (puede tardar 3-5 minutos)...
    "%PYEXE%" -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Falló la instalación de dependencias.
        echo         Revisa la conexión a internet e intenta otra vez.
        pause
        exit /b 1
    )
    "%PYEXE%" -m pip install --quiet -e .
    echo.
    echo ==========================================================
    echo  Entorno listo. Abriendo la aplicacion...
    echo ==========================================================
    echo.
)

set PYTHONPATH=src

echo.
echo Abriendo Dra Cami Contractual en tu navegador...
echo (No cierres esta ventana mientras uses el programa.)
echo.

"%PYEXE%" -m secop_ii.launcher

echo.
echo Programa cerrado. Puedes cerrar esta ventana.
pause
