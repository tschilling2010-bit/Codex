@echo off
echo HefterPro wird gestartet...

where python >nul 2>nul
if errorlevel 1 (
    echo Python nicht gefunden! Bitte installiere Python von https://python.org
    pause
    exit /b 1
)

if exist ".venv" (
    echo Loesche alte virtuelle Umgebung...
    rmdir /s /q .venv
)
echo Erstelle virtuelle Umgebung...
python -m venv .venv

call .venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install --prefer-binary -r requirements.txt -q
if errorlevel 1 (
    echo Fehler beim Installieren. Versuche alternativen Weg...
    pip install --prefer-binary fastapi uvicorn[standard] python-multipart Pillow reportlab pypdf pydantic -q
)

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
