@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv
)
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --clean --onedir --noconsole --name AutoClicker ^
  --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  --collect-all customtkinter ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import pynput.mouse._win32 ^
  main.py

echo.
echo Done. Your exe is at: dist\AutoClicker.exe
pause
