@echo off
title bambuPet
cd /d C:\Users\edmax\bambuPet

if not exist .venv (
    echo [bambuPet] Creando entorno virtual...
    python -m venv .venv
)

call .venv\Scripts\activate

if not exist requirements.txt (
    echo [bambuPet] ERROR: No se encuentra requirements.txt
    pause
    exit /b 1
)

pip install -r requirements.txt -q

if not exist config.json (
    echo [bambuPet] ERROR: No se encuentra config.json
    pause
    exit /b 1
)

echo [bambuPet] Iniciando widget...
python main.py
