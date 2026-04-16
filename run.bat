@echo off
echo HefterPro wird gestartet...

where python >nul 2>nul
if errorlevel 1 (
    echo Python nicht gefunden! Bitte installiere Python von https://python.org
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Erstelle virtuelle Umgebung...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt -q

set HEFTERPRO_STORAGE=%CD%\backend\storage
if not exist "%HEFTERPRO_STORAGE%" mkdir "%HEFTERPRO_STORAGE%"

echo.
echo HefterPro laeuft jetzt! Oeffne deinen Browser und gehe zu:
echo http://localhost:8000
echo.
echo Zum Beenden: Strg+C druecken
echo.

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
