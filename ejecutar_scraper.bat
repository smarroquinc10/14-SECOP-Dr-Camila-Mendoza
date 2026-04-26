@echo off
REM ============================================================
REM  Scraper masivo del portal SECOP — community.secop.gov.co
REM  Cierra el gap cardinal de 265 procesos sin cobertura API.
REM  La Dra / IT hace doble-click para correr este scrape ~2-4h.
REM
REM  IMPORTANTE: este scrape requiere INTERACCION HUMANA cuando
REM  el captcha de Google reCaptcha aparece y los solvers
REM  automaticos (Whisper / Google Speech) fallan. Chrome se va
REM  a abrir visible y vas a tener que resolver captchas a mano
REM  ocasionalmente. NO cerrar la ventana mientras corre.
REM ============================================================

@echo on
setlocal
cd /d "%~dp0"

set "VENV=.venv"
set "PYEXE=%VENV%\Scripts\python.exe"

REM --- Verificar venv ---
if not exist "%PYEXE%" (
    echo [ERROR] No existe %VENV%\Scripts\python.exe
    echo Ejecuta primero: ejecutar_pro.bat para crear el entorno
    pause
    exit /b 1
)

set PYTHONPATH=src

echo.
echo ============================================================
echo  SCRAPE MASIVO PORTAL SECOP — Dashboard FEAB
echo ============================================================
echo.
echo  - Procesa los procesos del watch list que NO estan en API
echo    publica (datos.gov.co). ETA: ~2-4 horas para 265 procs.
echo  - Chrome se abrira visible. Si aparece captcha que los
echo    solvers automaticos no resuelven, la ventana espera
echo    180s para que lo resuelvas a mano.
echo  - Progreso en tiempo real en .cache\portal_progress.jsonl
echo  - Resultado va a .cache\portal_opportunity.json
echo.
echo  Para INTERRUMPIR: Ctrl+C en esta consola (el progreso ya
echo  guardado se conserva, podes retomar despues).
echo.
pause

echo.
echo Iniciando scrape...
echo.

"%PYEXE%" -X utf8 scripts\scrape_portal.py --progress-file .cache\portal_progress.jsonl

echo.
echo ============================================================
echo  Scrape completado. Revisa el reporte:
echo    type .cache\portal_progress.jsonl ^| more
echo.
echo  Para subir el seed actualizado al dashboard:
echo    1. Copia .cache\portal_opportunity.json a app\public\data\portal_opportunity_seed.json
echo    2. git add app\public\data\portal_opportunity_seed.json
echo    3. git commit -m "feat(scrape): cierre gap cardinal — N procesos del portal"
echo    4. git push
echo.
echo  Despues, GitHub Action Deploy a Pages corre solo y la Dra
echo  ve los procesos enriquecidos en el dashboard live.
echo ============================================================
echo.
pause
