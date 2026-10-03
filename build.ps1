# build.ps1 - Compila MakeSign (ejecutar desde la raíz de HandTalk/)

$modo = Read-Host "¿Compilar en (L)impio o para (P)ruebas? [L/P]"
$modo = $modo.Trim().ToUpper()
if ($modo -notin @("L", "P")) {
    Write-Host "Opción no válida. Usa L o P." -ForegroundColor Red
    exit 1
}

# Siempre se empaquetan los HTML (web_server.py los busca en _internal)
$args_py = @(
    "--noconfirm", "--onedir", "--console",
    "--name", "MakeSign",
    "--icon", "assets/makesign.ico",
    "--paths=.", "--paths=inicio",
    "--add-data", "login.html;.",
    "--add-data", "visor.html;.",
    "--add-data", "index.html;.",
    "--collect-all", "mediapipe",
    "--collect-submodules", "uvicorn",
    "--hidden-import", "websockets"
)


pyinstaller @args_py inicio/menu_universal.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "La compilación falló." -ForegroundColor Red
    exit 1
}

$dist = "dist\MakeSign"


if ($modo -eq "P") {
    # Copia de datos a raiz, donde web_server.py los busca con __file__
    foreach ($carpeta in @("models", "custom_dataset", "sketches", "assets", "drivers")) {
        Copy-Item $carpeta -Destination "$dist" -Recurse -Force
    }
    Write-Host "Listo (pruebas): datos copiados a $dist" -ForegroundColor Yellow
} else {
    # Copia unicamente la carpeta assets y drivers, que son necesarias para la ejecución limpia
    Copy-Item assets -Destination $dist -Recurse -Force
    Copy-Item drivers -Destination $dist -Recurse -Force

    Write-Host "Listo (limpio): $dist\MakeSign.exe" -ForegroundColor Green
}