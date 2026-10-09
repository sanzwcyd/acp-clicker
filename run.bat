@echo off
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
python main.py
