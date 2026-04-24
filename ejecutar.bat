@echo off
REM ejecutar.bat - Doble clic para abrir la interfaz web del CRM SECOP II.
REM
REM Requisito: haber corrido setup.ps1 al menos una vez en esta carpeta.

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

echo.
echo Abriendo CRM SECOP II en tu navegador...
echo (Esta ventana debe quedarse abierta mientras usas el programa)
echo.

".venv\Scripts\python.exe" -m secop_ii.launcher

echo.
echo Programa cerrado. Puedes cerrar esta ventana.
pause
