@echo off
:: ==============================================================================
:: Unity Capture - Desregistro de Filtro DirectShow para HandTalk
:: ==============================================================================
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Este script requiere permisos de Administrador.
    echo Por favor haga clic derecho y seleccione "Ejecutar como administrador".
    pause
    exit /b 1
)

echo Desregistrando Unity Capture Filter...
if exist "UnityCaptureFilter64.dll" (
    regsvr32 /u /s "UnityCaptureFilter64.dll"
)
if exist "UnityCaptureFilter32.dll" (
    regsvr32 /u /s "UnityCaptureFilter32.dll"
)

echo [OK] Filtro DirectShow desregistrado exitosamente.
pause
