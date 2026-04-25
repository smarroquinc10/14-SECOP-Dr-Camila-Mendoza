@echo off
REM Update one-liner para el dashboard FEAB (HTML pura).
REM Uso:  update.bat "tu mensaje del cambio"
REM
REM Stagea + commitea + pushea. CI deploya a GitHub Pages en ~3 min.
REM Cami refresca el browser y ve la nueva versi�n.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1" %*
