@echo off
REM Refresca los seeds del dashboard desde el cache local.
REM
REM Despu�s de correr el portal scraper (Playwright) en el MSI dev,
REM corr� esto para copiar los archivos a app/public/data/.
REM
REM Uso:  refresh-seeds.bat
REM       update.bat "actualizado portal cache con N procesos"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\refresh-seeds.ps1" %*
