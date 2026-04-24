@echo off
REM actualizar-excel.bat - Arrastra tu archivo .xlsx sobre este .bat para actualizarlo.
REM
REM Tambien puedes hacer doble clic: te preguntara la ruta.

setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] No encuentro el entorno virtual .venv
    echo         Corre primero: powershell -ExecutionPolicy Bypass -File setup.ps1
    echo.
    pause
    exit /b 1
)

set PYTHONPATH=src

if "%~1"=="" (
    echo.
    set /p "ARCHIVO=Arrastra aqui tu Excel o escribe la ruta completa y presiona Enter: "
    set "TARGET=%ARCHIVO%"
) else (
    set "TARGET=%~1"
)

if not exist "%TARGET%" (
    echo.
    echo [ERROR] No encuentro el archivo: %TARGET%
    echo.
    pause
    exit /b 1
)

echo.
echo Actualizando "%TARGET%"...
echo (Se creara un backup automatico al lado del original)
echo.

".venv\Scripts\python.exe" -m secop_ii update-excel "%TARGET%" -v

echo.
pause
