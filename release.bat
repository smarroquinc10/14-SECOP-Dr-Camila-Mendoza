@echo off
REM Release one-liner para Dra Cami Contractual.
REM Uso:  release.bat "tu mensaje del release"
REM      release.bat -Minor "feature nuevo"
REM      release.bat -Version 1.2.3 "release especifico"
REM
REM Esto re-invoca a scripts\release.ps1 con todos los argumentos. La l�gica
REM real vive ah�.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\release.ps1" %*
