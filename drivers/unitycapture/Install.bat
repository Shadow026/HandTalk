@echo off
:: ==============================================================================
:: Unity Capture - Registro de Filtro DirectShow para HandTalk
:: ==============================================================================
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Este script requiere permisos de Administrador.
    echo Por favor haga clic derecho y seleccione "Ejecutar como administrador".
    pause
    exit /b 1
)

echo Registrando Unity Capture Filter (64-bit y 32-bit)...
if exist "UnityCaptureFilter64.dll" (
    regsvr32 /s "UnityCaptureFilter64.dll"
)
if exist "UnityCaptureFilter32.dll" (
    regsvr32 /s "UnityCaptureFilter32.dll"
)

echo [OK] Filtro DirectShow registrado exitosamente.
echo El dispositivo "Unity Video Capture" ahora esta disponible en Windows.
pause
