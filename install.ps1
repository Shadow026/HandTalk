# ==============================================================================
# HandTalk - Instalador y Gestor de Entorno Automatizado (Microsoft Windows)
# ==============================================================================
# Repositorio: HandTalk
# Descripción: Menú interactivo TUI centrado para la instalación, gestión de
#              entorno virtual (Python 3.10-3.12), dependencias de visión
#              artificial y generación de atajos CLI para HandTalk en Windows.
# Compatibilidad: Windows PowerShell 5.1 y PowerShell Core (7+).
#
# Nota de ejecución:
# Si PowerShell restringe la ejecución de scripts por ExecutionPolicy, ejecute:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# ==============================================================================

# Configuración de codificación de consola para visualización correcta
try {
    chcp.com 65001 | Out-Null
} catch { }

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    if ([Console]::InputEncoding) {
        [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    }
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# Definición segura de caracteres Unicode para marcos y símbolos (evita fallos de tokenizado ANSI en PowerShell 5.1)
$Script:ChH   = [char]0x2500  # Horizontal box line
$Script:ChV   = [char]0x2502  # Vertical box line
$Script:ChTL  = [char]0x250C  # Top-left corner
$Script:ChTR  = [char]0x2510  # Top-right corner
$Script:ChBL  = [char]0x2514  # Bottom-left corner
$Script:ChBR  = [char]0x2518  # Bottom-right corner
$Script:ChML  = [char]0x251C  # Middle-left divider
$Script:ChMR  = [char]0x2524  # Middle-right divider
$Script:ChDot = [char]0x2022  # Bullet
$Script:ChArr = [char]0x2192  # Arrow
$Script:ChOk  = [char]0x2713  # Check
$Script:ChErr = [char]0x2717  # Cross
$Script:ChWrn = [char]0x26A0  # Warning
$Script:ChInf = [char]0x2139  # Info

# Variables de rutas del proyecto
$Script:ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Script:VenvDir = Join-Path $Script:ProjectRoot "venv"
$Script:RequirementsFile = Join-Path $Script:ProjectRoot "inicio\requirements.txt"
$Script:LogFile = Join-Path $env:TEMP "handtalk_install.log"
$Script:BinDir = Join-Path $env:USERPROFILE ".handtalk\bin"

# --- Funciones de Centrado y Diseño TUI ---

function Get-ConsoleWidth {
    $width = 80
    try {
        if ($Host -and $Host.UI -and $Host.UI.RawUI) {
            $width = $Host.UI.RawUI.WindowSize.Width
        }
    } catch {
        $width = 80
    }
    if ($width -lt 20) { $width = 80 }
    return $width
}

function Strip-Ansi {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return "" }
    $clean = $Text -replace '\x1B\[[0-9;]*[a-zA-Z]', ''
    $clean = $clean -replace '`e\[[0-9;]*[a-zA-Z]', ''
    return $clean
}

function Write-Centered {
    param(
        [string]$Text = "",
        [string]$ForegroundColor = "",
        [switch]$NoNewline
    )
    if ([string]::IsNullOrEmpty($Text)) {
        Write-Host ""
        return
    }
    $width = Get-ConsoleWidth
    $clean = Strip-Ansi $Text
    $pad = [Math]::Max(0, [int][Math]::Floor(($width - $clean.Length) / 2))
    $spaces = " " * $pad
    if ($ForegroundColor -ne "") {
        if ($NoNewline) {
            Write-Host "$spaces$Text" -ForegroundColor $ForegroundColor -NoNewline
        } else {
            Write-Host "$spaces$Text" -ForegroundColor $ForegroundColor
        }
    } else {
        if ($NoNewline) {
            Write-Host "$spaces$Text" -NoNewline
        } else {
            Write-Host "$spaces$Text"
        }
    }
}

function Write-BoxTop {
    $border = "$($Script:ChH)" * 64
    $line = "$($Script:ChTL)$border$($Script:ChTR)"
    Write-Centered -Text $line -ForegroundColor Cyan
}

function Write-BoxSep {
    $border = "$($Script:ChH)" * 64
    $line = "$($Script:ChML)$border$($Script:ChMR)"
    Write-Centered -Text $line -ForegroundColor Cyan
}

function Write-BoxBottom {
    $border = "$($Script:ChH)" * 64
    $line = "$($Script:ChBL)$border$($Script:ChBR)"
    Write-Centered -Text $line -ForegroundColor Cyan
}

function Write-BoxRow {
    param(
        [string]$Text = "",
        [string]$Align = "center",
        [string]$ForegroundColor = "White"
    )
    $innerWidth = 64
    $clean = Strip-Ansi $Text
    $len = $clean.Length
    $padLeft = 0
    $padRight = 0

    if ($Align -eq "left") {
        $padLeft = 3
        $padRight = [Math]::Max(0, $innerWidth - $len - $padLeft)
    } elseif ($Align -eq "left_tight") {
        $padLeft = 1
        $padRight = [Math]::Max(0, $innerWidth - $len - $padLeft)
    } else {
        $padLeft = [Math]::Max(0, [int][Math]::Floor(($innerWidth - $len) / 2))
        $padRight = [Math]::Max(0, $innerWidth - $len - $padLeft)
    }

    $leftSpaces = " " * $padLeft
    $rightSpaces = " " * $padRight
    $content = "$leftSpaces$Text$rightSpaces"

    $width = Get-ConsoleWidth
    $boxLen = 66
    $boxPad = [Math]::Max(0, [int][Math]::Floor(($width - $boxLen) / 2))
    $outerSpaces = " " * $boxPad

    Write-Host "$outerSpaces" -NoNewline
    Write-Host "$($Script:ChV)" -ForegroundColor Cyan -NoNewline
    if ($ForegroundColor -ne "") {
        Write-Host "$content" -ForegroundColor $ForegroundColor -NoNewline
    } else {
        Write-Host "$content" -NoNewline
    }
    Write-Host "$($Script:ChV)" -ForegroundColor Cyan
}

# --- Banners Visuales ---

function Show-HeaderBanner {
    try { Clear-Host } catch { Write-Host "`n`n" }
    Write-Centered ""
    Write-BoxTop
    Write-BoxRow "   _   _    _    _   _ ____ _____  _    _     _  __             " "center" "White"
    Write-BoxRow "  | | | |  / \  | \ | |  _ \_   _|/ \  | |   | |/ /             " "center" "White"
    Write-BoxRow "  | |_| | / _ \ |  \| | | | || | / _ \ | |   | ' /              " "center" "White"
    Write-BoxRow "  |  _  |/ ___ \| |\  | |_| || |/ ___ \| |___| . \              " "center" "White"
    Write-BoxRow "  |_| |_/_/   \_\_| \_|____/ |_/_/   \_\_____|_|\_\             " "center" "White"
    Write-BoxRow "                                                                " "center" "White"
    Write-BoxRow "        Sistema de Reconocimiento y Traducción de Señas         " "center" "Yellow"
    Write-BoxRow "        MediaPipe 0.10.14  $($Script:ChDot)  OpenCV  $($Script:ChDot)  Scikit-Learn           " "center" "DarkGray"
    Write-BoxBottom
    Write-Centered ""
}

function Show-MainMenu {
    Write-BoxTop
    Write-BoxRow "MENU PRINCIPAL DE GESTION (WINDOWS)" "center" "White"
    Write-BoxSep
    Write-BoxRow "" "center" "White"
    Write-BoxRow "[1]  Instalación Completa  (Entorno + Dependencias + Atajos)" "left" "Green"
    Write-BoxRow "[2]  Desinstalación Total  (Eliminar venv y atajos CLI)" "left" "Yellow"
    Write-BoxRow "[3]  Salir" "left" "Red"
    Write-BoxRow "" "center" "White"
    Write-BoxBottom
    Write-Centered ""
}

function Prompt-Centered {
    param(
        [string]$PromptText,
        [string]$ForegroundColor = "Cyan"
    )
    $width = Get-ConsoleWidth
    $clean = Strip-Ansi $PromptText
    $pad = [Math]::Max(0, [int][Math]::Floor(($width - $clean.Length) / 2))
    $spaces = " " * $pad
    Write-Host "$spaces$PromptText" -ForegroundColor $ForegroundColor -NoNewline
}

function Wait-Enter {
    Write-Centered ""
    Prompt-Centered "Presione [Enter] para continuar..." "DarkGray"
    [void][System.Console]::ReadLine()
}

# --- Detección y Validación de Python en Windows ---

function Find-CompatiblePython {
    # 1. Probar mediante el Python Launcher para Windows (py.exe)
    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $flags = @("-3.12", "-3.11", "-3.10")
        foreach ($flag in $flags) {
            try {
                $code = "import sys; print(f'{sys.version_info.major} {sys.version_info.minor} {sys.executable}')"
                $res = & py $flag -c $code 2>$null
                if ($LASTEXITCODE -eq 0 -and $res) {
                    $parts = ($res -split '\s+').Trim()
                    if ($parts.Length -ge 3) {
                        $maj = [int]$parts[0]
                        $min = [int]$parts[1]
                        $exe = $parts[2..($parts.Length-1)] -join ' '
                        if ($maj -eq 3 -and ($min -ge 10 -and $min -le 12) -and (Test-Path $exe)) {
                            return @{
                                Executable = $exe
                                Version = "3.$min"
                                Source = "Python Launcher ($flag)"
                            }
                        }
                    }
                }
            } catch { }
        }
    }

    # 2. Probar mediante binarios directos en PATH
    $cmdCandidates = @("python3.12", "python3.11", "python3.10", "python", "python3")
    foreach ($cmd in $cmdCandidates) {
        try {
            $cmdObj = Get-Command $cmd -ErrorAction SilentlyContinue
            if ($cmdObj) {
                $cmdExe = if ($cmdObj.Path) { $cmdObj.Path } elseif ($cmdObj.Source) { $cmdObj.Source } else { $cmd }
                $code = "import sys; print(f'{sys.version_info.major} {sys.version_info.minor} {sys.executable}')"
                $res = & $cmdExe -c $code 2>$null
                if ($LASTEXITCODE -eq 0 -and $res) {
                    $parts = ($res -split '\s+').Trim()
                    if ($parts.Length -ge 3) {
                        $maj = [int]$parts[0]
                        $min = [int]$parts[1]
                        $exe = $parts[2..($parts.Length-1)] -join ' '
                        if ($maj -eq 3 -and ($min -ge 10 -and $min -le 12) -and (Test-Path $exe)) {
                            return @{
                                Executable = $exe
                                Version = "3.$min"
                                Source = "$cmd ($exe)"
                            }
                        }
                    }
                }
            }
        } catch { }
    }

    # 3. Probar rutas comunes de instalación en Windows (si no están añadidas al PATH)
    $commonDirs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python310\python.exe"
    )
    foreach ($candExe in $commonDirs) {
        if (Test-Path $candExe) {
            try {
                $code = "import sys; print(f'{sys.version_info.major} {sys.version_info.minor} {sys.executable}')"
                $res = & $candExe -c $code 2>$null
                if ($LASTEXITCODE -eq 0 -and $res) {
                    $parts = ($res -split '\s+').Trim()
                    if ($parts.Length -ge 3) {
                        $maj = [int]$parts[0]
                        $min = [int]$parts[1]
                        $exe = $parts[2..($parts.Length-1)] -join ' '
                        if ($maj -eq 3 -and ($min -ge 10 -and $min -le 12) -and (Test-Path $exe)) {
                            return @{
                                Executable = $exe
                                Version = "3.$min"
                                Source = "Ruta estándar ($exe)"
                            }
                        }
                    }
                }
            } catch { }
        }
    }

    return $null
}

# --- Creación de Atajos CLI en Windows (.bat wrappers) ---

function Create-CliShortcuts {
    param([string]$VenvPython)

    if (-not (Test-Path $Script:BinDir)) {
        New-Item -ItemType Directory -Path $Script:BinDir -Force | Out-Null
    }

    $shortcuts = @(
        @{ Name = "handtalk-captura"; Target = "inicio\gui_captura.py"; Desc = "Captura de señas" },
        @{ Name = "handtalk-entrenar"; Target = "inicio\train_classifier.py"; Desc = "Entrenamiento de modelo" },
        @{ Name = "handtalk-traducir"; Target = "inicio\realtime_translator.py"; Desc = "Traduccion en vivo" }
    )

    foreach ($item in $shortcuts) {
        $batPath = Join-Path $Script:BinDir "$($item.Name).bat"
        $scriptPath = Join-Path $Script:ProjectRoot $item.Target

        $batContent = @"
@echo off
setlocal
cd /d "$Script:ProjectRoot"
"$VenvPython" "$scriptPath" %*
endlocal
"@
        Set-Content -Path $batPath -Value $batContent -Encoding ASCII
    }

    # Agregar la carpeta de binarios al PATH de Usuario si no existe
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($null -eq $userPath) { $userPath = "" }
    $parts = $userPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    
    if ($parts -notcontains $Script:BinDir) {
        $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) {
            $Script:BinDir
        } else {
            "$userPath;$Script:BinDir"
        }
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    }

    # Actualizar PATH de la sesión actual
    $sessionParts = $env:PATH -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if ($sessionParts -notcontains $Script:BinDir) {
        $env:PATH = "$Script:BinDir;$env:PATH"
    }
}

function Remove-CliShortcuts {
    $shortcuts = @("handtalk-captura.bat", "handtalk-entrenar.bat", "handtalk-traducir.bat")
    foreach ($sc in $shortcuts) {
        $scPath = Join-Path $Script:BinDir $sc
        if (Test-Path $scPath) {
            Remove-Item -Path $scPath -Force -ErrorAction SilentlyContinue
        }
    }

    # Si la carpeta .handtalk\bin queda vacía, eliminarla ordenadamente
    if (Test-Path $Script:BinDir) {
        $items = Get-ChildItem -Path $Script:BinDir -ErrorAction SilentlyContinue
        if (-not $items) {
            Remove-Item -Path $Script:BinDir -Force -Recurse -ErrorAction SilentlyContinue
            $parent = Split-Path $Script:BinDir -Parent
            $parentItems = Get-ChildItem -Path $parent -ErrorAction SilentlyContinue
            if (-not $parentItems) {
                Remove-Item -Path $parent -Force -Recurse -ErrorAction SilentlyContinue
            }
        }
    }

    # Remover del PATH de Usuario
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -like "*$Script:BinDir*") {
        $parts = $userPath -split ';' | Where-Object {
            $_ -ne $Script:BinDir -and (-not [string]::IsNullOrWhiteSpace($_))
        }
        $newPath = $parts -join ';'
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    }
}

# --- Acción 1: Instalación Completa ---

function Start-Installation {
    Show-HeaderBanner
    Write-BoxTop
    Write-BoxRow "PROCESO DE INSTALACION COMPLETA (WINDOWS)" "center" "White"
    Write-BoxBottom
    Write-Centered ""

    # 1. Detección de Python compatible
    Write-Centered "[1/5] Buscando intérprete Python compatible (3.10 - 3.12)..." "Cyan"
    $pyInfo = Find-CompatiblePython

    if (-not $pyInfo) {
        Write-Centered ""
        Write-BoxTop
        Write-BoxRow "$($Script:ChErr) ERROR: VERSION DE PYTHON NO COMPATIBLE" "center" "Red"
        Write-BoxSep
        Write-BoxRow "MediaPipe 0.10.14 requiere Python 3.10, 3.11 o 3.12." "center" "White"
        Write-BoxRow "Python 3.13+ o <3.10 NO poseen compatibilidad de wheels." "center" "Yellow"
        Write-BoxRow "" "center" "White"
        Write-BoxRow "Opciones recomendadas para Windows:" "left" "Cyan"
        Write-BoxRow "  $($Script:ChDot) winget install -e --id Python.Python.3.11" "left_tight" "White"
        Write-BoxRow "  $($Script:ChDot) Descargar instalador de Python 3.11 desde python.org:" "left_tight" "White"
        Write-BoxRow "    https://www.python.org/downloads/release/python-3119/" "left_tight" "DarkGray"
        Write-BoxRow "  $($Script:ChDot) Recuerde marcar: 'Add python.exe to PATH'." "left_tight" "Yellow"
        Write-BoxBottom
        Wait-Enter
        return
    }

    $pythonExe = $pyInfo.Executable
    $pythonVer = $pyInfo.Version
    Write-Centered "      $($Script:ChOk) Localizado: $pythonExe (v$pythonVer)" "Green"
    Write-Centered ""

    # 2. Creación del entorno virtual (venv)
    Write-Centered "[2/5] Configurando entorno virtual en: .\venv" "Cyan"
    if (Test-Path $Script:VenvDir) {
        Write-Centered "      $($Script:ChWrn) Ya existe un entorno virtual previo." "Yellow"
        Prompt-Centered "¿Desea recrearlo desde cero? [s/N]: " "White"
        $recreate = [System.Console]::ReadLine()
        if ($null -eq $recreate) { $recreate = "" }
        if ($recreate -match '^[sSyY]') {
            Write-Centered "      Eliminando entorno anterior..." "DarkGray"
            Remove-Item -Path $Script:VenvDir -Recurse -Force
            & $pythonExe -m venv $Script:VenvDir *>"$Script:LogFile"
        } else {
            Write-Centered "      $($Script:ChInf) Conservando entorno virtual existente." "Cyan"
        }
    } else {
        & $pythonExe -m venv $Script:VenvDir *>"$Script:LogFile"
    }

    $venvPython = Join-Path $Script:VenvDir "Scripts\python.exe"
    $venvPip = Join-Path $Script:VenvDir "Scripts\pip.exe"

    if (-not (Test-Path $venvPython)) {
        Write-Centered "      $($Script:ChErr) Error al generar entorno virtual. Revise $Script:LogFile" "Red"
        Wait-Enter
        return
    }
    Write-Centered "      $($Script:ChOk) Entorno virtual preparado con éxito." "Green"
    Write-Centered ""

    # 3. Actualización de pip, setuptools y wheel
    Write-Centered "[3/5] Actualizando pip, setuptools y wheel..." "Cyan"
    & $venvPython -m pip install --upgrade pip setuptools wheel *>>"$Script:LogFile"
    if ($LASTEXITCODE -ne 0) {
        Write-Centered "      $($Script:ChWrn) Advertencia al actualizar pip; continuando..." "Yellow"
    } else {
        Write-Centered "      $($Script:ChOk) Gestores de paquetes actualizados." "Green"
    }
    Write-Centered ""

    # 4. Instalación de dependencias
    Write-Centered "[4/5] Instalando dependencias desde inicio\requirements.txt..." "Cyan"
    Write-Centered "      (Esto puede tomar unos momentos según la conexión de red)" "DarkGray"

    & $venvPip install -r $Script:RequirementsFile *>>"$Script:LogFile"
    if ($LASTEXITCODE -ne 0) {
        Write-Centered ""
        Write-BoxTop
        Write-BoxRow "$($Script:ChErr) ERROR AL INSTALAR DEPENDENCIAS" "center" "Red"
        Write-BoxSep
        Write-BoxRow "Hubo un problema al descargar o compilar las librerías." "center" "White"
        Write-BoxRow "Consulte los detalles en el archivo de registro:" "center" "DarkGray"
        Write-BoxRow "$Script:LogFile" "center" "Yellow"
        Write-BoxBottom
        Wait-Enter
        return
    }
    Write-Centered "      $($Script:ChOk) Dependencias instaladas correctamente." "Green"
    Write-Centered ""

    # 5. Creación de Atajos CLI
    Write-Centered "[5/5] Generando atajos de terminal en $Script:BinDir..." "Cyan"
    Create-CliShortcuts -VenvPython $venvPython
    Write-Centered "      $($Script:ChOk) Atajos creados (.bat) y agregados al PATH del usuario." "Green"
    Write-Centered ""

    # 6. Verificación Post-Instalación (Smoke Test)
    Write-Centered "Ejecutando prueba rápida de importación de librerías..." "White"
    $smokeCode = "import cv2, mediapipe, sklearn, PIL, numpy; print('OK')"
    $smokeOut = & $venvPython -c $smokeCode 2>$null
    if ($smokeOut -eq "OK") {
        Write-Centered "      $($Script:ChOk) Todas las librerías clave importadas correctamente." "Green"
    } else {
        Write-Centered "      $($Script:ChWrn) Advertencia: Verifique los módulos en $Script:LogFile" "Yellow"
    }
    Write-Centered ""

    # Resumen de instalación
    Write-BoxTop
    Write-BoxRow "¡INSTALACION COMPLETADA CON EXITO!" "center" "Green"
    Write-BoxSep
    Write-BoxRow "Ya puede invocar HandTalk directamente desde CMD o PowerShell:" "center" "White"
    Write-BoxRow "" "center" "White"
    Write-BoxRow "  1. handtalk-captura   $($Script:ChArr) Captura y recolección de señas" "left_tight" "Cyan"
    Write-BoxRow "  2. handtalk-entrenar  $($Script:ChArr) Entrenamiento del clasificador" "left_tight" "Cyan"
    Write-BoxRow "  3. handtalk-traducir  $($Script:ChArr) Traducción en tiempo real (cámara)" "left_tight" "Cyan"
    Write-BoxRow "" "center" "White"
    Write-BoxRow "Nota: Si abre una terminal nueva y los comandos no responden," "center" "DarkGray"
    Write-BoxRow "reinicie la terminal para refrescar el PATH del sistema." "center" "DarkGray"
    Write-BoxBottom

    Wait-Enter
}

# --- Acción 2: Desinstalación ---

function Start-Uninstallation {
    Show-HeaderBanner
    Write-BoxTop
    Write-BoxRow "DESINSTALACION DE HANDTALK" "center" "Yellow"
    Write-BoxSep
    Write-BoxRow "Esta acción eliminará el entorno virtual (.\venv)" "center" "White"
    Write-BoxRow "y los atajos creados en $($Script:BinDir)." "center" "White"
    Write-BoxBottom
    Write-Centered ""

    Prompt-Centered "¿Está seguro de que desea desinstalar HandTalk? [s/N]: " "Red"
    $confirm = [System.Console]::ReadLine()
    if ($null -eq $confirm) { $confirm = "" }
    if ($confirm -notmatch '^[sSyY]') {
        Write-Centered ""
        Write-Centered "Operación cancelada. No se realizaron modificaciones." "Yellow"
        Wait-Enter
        return
    }

    Write-Centered ""
    Write-Centered "[1/3] Eliminando entorno virtual .\venv..." "Cyan"
    if (Test-Path $Script:VenvDir) {
        Remove-Item -Path $Script:VenvDir -Recurse -Force
        Write-Centered "      $($Script:ChOk) Entorno virtual eliminado." "Green"
    } else {
        Write-Centered "      $($Script:ChInf) No se encontró carpeta venv\." "DarkGray"
    }

    Write-Centered "[2/3] Eliminando atajos de terminal en $($Script:BinDir)..." "Cyan"
    Remove-CliShortcuts
    Write-Centered "      $($Script:ChOk) Atajos eliminados." "Green"

    Write-Centered "[3/3] Limpiando configuraciones de PATH del usuario..." "Cyan"
    Write-Centered "      $($Script:ChOk) Registro de PATH actualizado." "Green"
    Write-Centered ""

    Write-BoxTop
    Write-BoxRow "DESINSTALACION COMPLETADA" "center" "Green"
    Write-BoxSep
    Write-BoxRow "Todos los componentes generados han sido retirados." "center" "White"
    Write-BoxRow "Sus datos y modelos entrenados se mantienen intactos." "center" "DarkGray"
    Write-BoxBottom

    Wait-Enter
}

# --- Bucle Principal del Menú ---

function Main {
    do {
        Show-HeaderBanner
        Show-MainMenu
        Prompt-Centered "Seleccione una opción [1-3]: " "Cyan"
        $choice = [System.Console]::ReadLine()
        if ($null -eq $choice) { $choice = "" }

        switch ($choice.Trim()) {
            "1" {
                Start-Installation
            }
            "2" {
                Start-Uninstallation
            }
            "3" {
                Show-HeaderBanner
                Write-BoxTop
                Write-BoxRow "¡GRACIAS POR USAR HANDTALK!" "center" "White"
                Write-BoxSep
                Write-BoxRow "Lenguaje de Señas Potenciado con Visión e IA" "center" "DarkGray"
                Write-BoxBottom
                Write-Centered ""
                return
            }
            default {
                Write-Centered ""
                Write-Centered "Opción no válida. Ingrese 1, 2 o 3." "Red"
                Start-Sleep -Milliseconds 1200
            }
        }
    } while ($true)
}

Main
