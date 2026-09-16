@echo off
chcp 65001 >nul 2>&1
title bambuPet v0.4.0 (Tkinter)
cd /d %~dp0

echo.
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~
echo    bambuPet v0.4.0
echo    Tkinter Widget
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~

:: Usar Python 3.14 explícitamente
set "PYEXE=C:\Users\edmax\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%PYEXE%" (
    set "PYEXE=C:\Users\edmax\AppData\Local\Python\bin\python.exe"
)

if not defined PYEXE (
    echo.
    echo [ERROR] Python no encontrado
    echo.
    pause
    exit /b 1
)

echo Python: %PYEXE%

:: Tkinter es built-in, no hay deps externas
if not exist config.json (
    echo.
    echo [ERROR] Falta config.json
    pause
    exit /b 1
)

echo.
echo [OK] Iniciando...
echo.
echo   Click en el widget para configuracion
echo   Arrastra para mover
echo   ESC para cerrar
echo.

"%PYEXE%" app.py
set EC=%errorlevel%
echo.
if %EC% neq 0 (
    echo [ERROR] bambuPet termino con codigo: %EC%
    pause
)
