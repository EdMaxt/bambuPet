@echo off
chcp 65001 >nul 2>&1
title bambuPet v0.3.1
cd /d %~dp0

echo.
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~
echo    bambuPet v0.3.1
echo    Desktop Pet Widget
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~

:: Python 3.14 con PyQt5 instalado
set "PYEXE=C:\Users\edmax\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%PYEXE%" (
    echo.
    echo [ERROR] Python no encontrado en:
    echo %PYEXE%
    echo.
    pause
    exit /b 1
)
echo Python: %PYEXE%

:: Crear venv si no existe
if not exist .venv (
    echo [1/3] Creando entorno virtual...
    "%PYEXE%" -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Fallo crear venv
        pause
        exit /b 1
    )
)

:: Activar venv
call .venv\Scripts\activate.bat
echo [2/3] Entorno activado

:: Instalar deps
pip install -r requirements.txt -q
echo [3/3] Dependencias listas

if not exist config.json (
    echo.
    echo [ERROR] Falta config.json
    pause
    exit /b 1
)

echo.
echo [OK] Iniciando...
echo.
python main.py
set EC=%errorlevel%
echo.
if %EC% neq 0 echo [ERROR] Codigo: %EC%
pause
