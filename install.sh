#!/usr/bin/env bash
# ==============================================================================
# HandTalk - Instalador y Gestor de Entorno Automatizado (GNU/Linux)
# ==============================================================================
# Repositorio: HandTalk
# Descripción: Menú interactivo TUI centrado para la instalación, gestión de
#              entorno virtual (Python 3.10-3.12), dependencias de visión
#              artificial y generación de atajos CLI para HandTalk.
# ==============================================================================

set -u

# --- Directorios y Rutas Clave ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/inicio/requirements.txt"
LOG_FILE="/tmp/handtalk_install.log"
if ! touch "${LOG_FILE}" >/dev/null 2>&1; then
    LOG_FILE="${TMPDIR:-/tmp}/handtalk_install_${USER:-$(id -un 2>/dev/null || echo user)}.log"
fi
BIN_DIR="${HOME}/.local/bin"

# --- Paleta de Colores ANSI y Estilos ---
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_CYAN="\033[1;36m"
C_BLUE="\033[1;34m"
C_GREEN="\033[1;32m"
C_YELLOW="\033[1;33m"
C_RED="\033[1;31m"
C_WHITE="\033[1;37m"
C_GRAY="\033[0;90m"
C_MAGENTA="\033[1;35m"

# --- Manejo Limpio de Señales (SIGINT, SIGTERM) ---
cleanup_on_exit() {
    # Restaurar visibilidad del cursor y resetear colores
    tput cnorm 2>/dev/null || true
    printf "%b" "${C_RESET}"
}
trap cleanup_on_exit EXIT

handle_interrupt() {
    printf "\n\n"
    print_centered "${C_YELLOW}⚠ Operación interrumpida por el usuario.${C_RESET}"
    printf "\n"
    exit 130
}
trap handle_interrupt INT TERM

# --- Funciones de Centrado y Diseño TUI ---

get_terminal_width() {
    local width
    width=$(tput cols 2>/dev/null || echo 80)
    if [ -z "$width" ] || [ "$width" -lt 20 ]; then
        width=80
    fi
    echo "$width"
}

strip_ansi() {
    local input="$1"
    echo -e "$input" | sed -E "s/\x1B\[([0-9]{1,3}(;[0-9]{1,3})*)?[mGK]//g"
}

print_centered() {
    local text="${1:-}"
    if [ -z "$text" ]; then
        printf "\n"
        return
    fi
    local width
    width=$(get_terminal_width)
    local clean_text
    clean_text=$(strip_ansi "$text")
    local text_len=${#clean_text}
    local padding=$(( (width - text_len) / 2 ))
    if [ "$padding" -lt 0 ]; then padding=0; fi
    printf "%*s%b\n" "$padding" "" "$text"
}

print_box_top() {
    local border
    border=$(printf "─%.0s" $(seq 1 64))
    print_centered "${C_CYAN}┌${border}┐${C_RESET}"
}

print_box_sep() {
    local border
    border=$(printf "─%.0s" $(seq 1 64))
    print_centered "${C_CYAN}├${border}┤${C_RESET}"
}

print_box_bottom() {
    local border
    border=$(printf "─%.0s" $(seq 1 64))
    print_centered "${C_CYAN}└${border}┘${C_RESET}"
}

print_box_row() {
    local text="${1:-}"
    local align="${2:-center}"
    local inner_width=64
    local clean_text
    clean_text=$(strip_ansi "$text")
    local len=${#clean_text}
    local pad_left=0
    local pad_right=0

    if [ "$align" = "left" ]; then
        pad_left=3
        pad_right=$(( inner_width - len - pad_left ))
    elif [ "$align" = "left_tight" ]; then
        pad_left=1
        pad_right=$(( inner_width - len - pad_left ))
    else
        pad_left=$(( (inner_width - len) / 2 ))
        pad_right=$(( inner_width - len - pad_left ))
    fi

    if [ "$pad_left" -lt 0 ]; then pad_left=0; fi
    if [ "$pad_right" -lt 0 ]; then pad_right=0; fi

    local left_spaces=""
    if [ "$pad_left" -gt 0 ]; then left_spaces=$(printf "%*s" "$pad_left" ""); fi
    local right_spaces=""
    if [ "$pad_right" -gt 0 ]; then right_spaces=$(printf "%*s" "$pad_right" ""); fi

    print_centered "${C_CYAN}│${C_RESET}${left_spaces}${text}${right_spaces}${C_CYAN}│${C_RESET}"
}

# --- Banners Visuales ---

print_header_banner() {
    clear 2>/dev/null || printf "\n\n"
    print_centered ""
    print_centered "${C_CYAN}┌───────────────────────────────────────────────────────────────────────┐${C_RESET}"
    print_centered "${C_CYAN}│${C_WHITE}  ██╗  ██╗ █████╗ ███╗   ██╗██████╗ ████████╗ █████╗ ██╗     ██╗  ██╗  ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}│${C_WHITE}  ██║  ██║██╔══██╗████╗  ██║██╔══██╗╚══██╔══╝██╔══██╗██║     ██║ ██╔╝  ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}│${C_WHITE}  ███████║███████║██╔██╗ ██║██║  ██║   ██║   ███████║██║     █████╔╝   ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}│${C_WHITE}  ██╔══██║██╔══██║██║╚██╗██║██║  ██║   ██║   ██╔══██║██║     ██╔═██╗   ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}│${C_WHITE}  ██║  ██║██║  ██║██║ ╚████║██████╔╝   ██║   ██║  ██║███████╗██║  ██╗  ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}│${C_WHITE}  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝    ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝  ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}│                                                                       │${C_RESET}"
    print_centered "${C_CYAN}│${C_YELLOW}            Sistema de Reconocimiento y Traducción de Señas            ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}│${C_GRAY}             MediaPipe 0.10.14  •  OpenCV  •  Scikit-Learn             ${C_CYAN}│${C_RESET}"
    print_centered "${C_CYAN}└───────────────────────────────────────────────────────────────────────┘${C_RESET}"
    print_centered ""
}

print_menu() {
    print_box_top
    print_box_row "${C_WHITE}${C_BOLD}MENÚ PRINCIPAL DE GESTIÓN${C_RESET}" "center"
    print_box_sep
    print_box_row "" "center"
    print_box_row "${C_GREEN}[1]${C_WHITE}  Instalación Completa  ${C_GRAY}(Entorno + Dependencias + Atajos)${C_RESET}" "left"
    print_box_row "${C_CYAN}[2]${C_WHITE}  Actualizar Dependencias  ${C_GRAY}(Librerías nuevas en venv)${C_RESET}" "left"
    print_box_row "${C_YELLOW}[3]${C_WHITE}  Desinstalación Total  ${C_GRAY}(Eliminar venv y atajos CLI)${C_RESET}" "left"
    print_box_row "${C_RED}[4]${C_WHITE}  Salir${C_RESET}" "left"
    print_box_row "" "center"
    print_box_bottom
    print_centered ""
}

prompt_centered() {
    local prompt_text="$1"
    local clean_prompt
    clean_prompt=$(strip_ansi "$prompt_text")
    local width
    width=$(get_terminal_width)
    local pad=$(( (width - ${#clean_prompt}) / 2 ))
    if [ "$pad" -lt 0 ]; then pad=0; fi
    printf "%*s%b" "$pad" "" "$prompt_text"
}

wait_enter() {
    print_centered ""
    prompt_centered "${C_GRAY}Presione ${C_WHITE}[Enter]${C_GRAY} para continuar...${C_RESET}"
    # shellcheck disable=SC2162
    read -r dummy
}

# --- Lógica de Detección de Python Compatible ---

find_compatible_python() {
    local candidates=("python3.12" "python3.11" "python3.10" "python3" "python")
    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            local ver_output
            ver_output=$("$cmd" -c "import sys; print(f'{sys.version_info.major} {sys.version_info.minor} {sys.version.split()[0]}')" 2>/dev/null || true)
            if [ -n "$ver_output" ]; then
                local major minor full_ver
                major=$(echo "$ver_output" | awk '{print $1}')
                minor=$(echo "$ver_output" | awk '{print $2}')
                full_ver=$(echo "$ver_output" | awk '{print $3}')
                if [ "$major" -eq 3 ] && { [ "$minor" -eq 10 ] || [ "$minor" -eq 11 ] || [ "$minor" -eq 12 ]; }; then
                    DETECTED_PYTHON="$cmd"
                    DETECTED_PYTHON_VER="$full_ver"
                    return 0
                fi
            fi
        fi
    done
    return 1
}

verify_venv_module() {
    local python_bin="$1"
    "$python_bin" -c "import venv" >/dev/null 2>&1
}

# --- Gestión de Atajos CLI en Linux ---

create_cli_shortcuts() {
    mkdir -p "${BIN_DIR}"

    local shortcuts=(
        "handtalk-captura:inicio/gui_captura.py:Captura y recolección de señas personalizadas"
        "handtalk-entrenar:inicio/train_classifier.py:Entrenamiento del clasificador de señas"
        "handtalk-traducir:inicio/realtime_translator.py:Traducción de señas en vivo con cámara"
    )

    for item in "${shortcuts[@]}"; do
        local name target_script desc
        name=$(echo "$item" | cut -d':' -f1)
        target_script=$(echo "$item" | cut -d':' -f2)
        desc=$(echo "$item" | cut -d':' -f3)
        local shortcut_path="${BIN_DIR}/${name}"

        cat <<EOF > "${shortcut_path}"
#!/usr/bin/env bash
# ==============================================================================
# HandTalk Launcher: ${name}
# ${desc}
# ==============================================================================
set -e
PROJECT_DIR="${SCRIPT_DIR}"
cd "\${PROJECT_DIR}" || exit 1
exec "\${PROJECT_DIR}/venv/bin/python" "\${PROJECT_DIR}/${target_script}" "\$@"
EOF
        chmod +x "${shortcut_path}"
    done

    # Asegurar que ~/.local/bin esté en el PATH del usuario
    local marker_start="# >>> HandTalk CLI PATH >>>"
    local marker_end="# <<< HandTalk CLI PATH <<<"
    local path_line='export PATH="$HOME/.local/bin:$PATH"'

    # Añadir a la sesión actual
    case ":${PATH}:" in
        *":${BIN_DIR}:"*) ;;
        *) export PATH="${BIN_DIR}:${PATH}" ;;
    esac

    # Persistir en archivos rc disponibles
    for rc in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
        if [ -f "$rc" ]; then
            if ! grep -Fq "$marker_start" "$rc"; then
                printf "\n%s\n%s\n%s\n" "$marker_start" "$path_line" "$marker_end" >> "$rc"
            fi
        fi
    done
}

remove_cli_shortcuts() {
    local shortcuts=("handtalk-captura" "handtalk-entrenar" "handtalk-traducir")
    for name in "${shortcuts[@]}"; do
        local shortcut_path="${BIN_DIR}/${name}"
        if [ -f "${shortcut_path}" ]; then
            rm -f "${shortcut_path}"
        fi
    done

    # Limpiar líneas de PATH añadidas en rc files
    local marker_start="# >>> HandTalk CLI PATH >>>"
    local marker_end="# <<< HandTalk CLI PATH <<<"
    for rc in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
        if [ -f "$rc" ] && grep -Fq "$marker_start" "$rc"; then
            sed -i "/$marker_start/,/$marker_end/d" "$rc" 2>/dev/null || true
        fi
    done
}

# --- Acción 1: Instalación Completa ---

do_installation() {
    print_header_banner
    print_box_top
    print_box_row "${C_WHITE}${C_BOLD}PROCESO DE INSTALACIÓN COMPLETA${C_RESET}" "center"
    print_box_bottom
    print_centered ""

    # 1. Detección de Python compatible
    print_centered "${C_CYAN}[1/5]${C_WHITE} Buscando intérprete Python compatible (3.10 - 3.12)...${C_RESET}"
    if ! find_compatible_python; then
        print_centered ""
        print_box_top
        print_box_row "${C_RED}✗ ERROR: VERSIÓN DE PYTHON NO COMPATIBLE${C_RESET}" "center"
        print_box_sep
        print_box_row "${C_WHITE}MediaPipe 0.10.14 requiere Python 3.10, 3.11 o 3.12.${C_RESET}" "center"
        print_box_row "${C_YELLOW}Python 3.13+ o <3.10 NO poseen compatibilidad.${C_RESET}" "center"
        print_box_row "" "center"
        print_box_row "${C_CYAN}Instrucciones de instalación según su distribución:${C_RESET}" "left"
        print_box_row "  • Ubuntu/Debian:  sudo apt install python3.11 python3.11-venv" "left_tight"
        print_box_row "  • Arch Linux:     sudo pacman -S python311 (o via pyenv/AUR)" "left_tight"
        print_box_row "  • Fedora:         sudo dnf install python3.11" "left_tight"
        print_box_row "  • pyenv:          pyenv install 3.11.9 && pyenv local 3.11.9" "left_tight"
        print_box_bottom
        wait_enter
        return 1
    fi

    print_centered "      ${C_GREEN}✓${C_WHITE} Localizado: ${C_BOLD}${DETECTED_PYTHON}${C_RESET} ${C_GRAY}(v${DETECTED_PYTHON_VER})${C_RESET}"
    print_centered ""

    # Validar módulo venv
    if ! verify_venv_module "$DETECTED_PYTHON"; then
        print_box_top
        print_box_row "${C_RED}✗ ERROR: MÓDULO 'venv' NO ENCONTRADO${C_RESET}" "center"
        print_box_sep
        print_box_row "${C_WHITE}El intérprete ${DETECTED_PYTHON} no tiene instalado el paquete venv.${C_RESET}" "center"
        print_box_row "${C_YELLOW}Solución recomendada:${C_RESET}" "center"
        print_box_row "  sudo apt install python3-venv o python3.11-venv" "center"
        print_box_bottom
        wait_enter
        return 1
    fi

    # 2. Creación del entorno virtual
    print_centered "${C_CYAN}[2/5]${C_WHITE} Configurando entorno virtual en: ${C_GRAY}./venv${C_RESET}"
    if [ -d "${VENV_DIR}" ]; then
        print_centered "      ${C_YELLOW}⚠ Ya existe un entorno virtual previo.${C_RESET}"
        prompt_centered "${C_WHITE}¿Desea recrearlo desde cero? [s/N]: ${C_RESET}"
        # shellcheck disable=SC2162
        read -r recreate_opt
        if [[ "$recreate_opt" =~ ^[sS]$ ]]; then
            print_centered "      ${C_GRAY}Eliminando entorno virtual anterior...${C_RESET}"
            rm -rf "${VENV_DIR}"
            "$DETECTED_PYTHON" -m venv "${VENV_DIR}" >"${LOG_FILE}" 2>&1
        else
            print_centered "      ${C_CYAN}ℹ Conservando entorno virtual existente.${C_RESET}"
        fi
    else
        "$DETECTED_PYTHON" -m venv "${VENV_DIR}" >"${LOG_FILE}" 2>&1
    fi

    if [ ! -f "${VENV_DIR}/bin/python" ]; then
        print_centered "      ${C_RED}✗ Error al generar el entorno virtual. Revise ${LOG_FILE}${C_RESET}"
        wait_enter
        return 1
    fi
    print_centered "      ${C_GREEN}✓${C_WHITE} Entorno virtual preparado con éxito.${C_RESET}"
    print_centered ""

    # 3. Actualización de pip, setuptools y wheel
    print_centered "${C_CYAN}[3/5]${C_WHITE} Actualizando pip, setuptools y wheel...${C_RESET}"
    if ! "${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel >>"${LOG_FILE}" 2>&1; then
        print_centered "      ${C_YELLOW}⚠ Advertencia: No se pudo actualizar pip a la última versión.${C_RESET}"
    else
        print_centered "      ${C_GREEN}✓${C_WHITE} Gestores de paquetes actualizados.${C_RESET}"
    fi
    print_centered ""

    # 4. Instalación de dependencias
    print_centered "${C_CYAN}[4/5]${C_WHITE} Instalando dependencias desde ${C_GRAY}inicio/requirements.txt${C_RESET}..."
    print_centered "      ${C_GRAY}(Esto puede tomar unos momentos según su conexión)${C_RESET}"

    if ! "${VENV_DIR}/bin/pip" install -r "${REQUIREMENTS_FILE}" >>"${LOG_FILE}" 2>&1; then
        print_centered ""
        print_box_top
        print_box_row "${C_RED}✗ ERROR AL INSTALAR DEPENDENCIAS${C_RESET}" "center"
        print_box_sep
        print_box_row "${C_WHITE}Hubo un problema al descargar o compilar las librerías.${C_RESET}" "center"
        print_box_row "${C_GRAY}Consulte los detalles en el archivo de registro:${C_RESET}" "center"
        print_box_row "${C_YELLOW}${LOG_FILE}${C_RESET}" "center"
        print_box_bottom
        wait_enter
        return 1
    fi
    print_centered "      ${C_GREEN}✓${C_WHITE} Dependencias instaladas correctamente.${C_RESET}"
    print_centered ""

    # 5. Creación de Atajos CLI
    print_centered "${C_CYAN}[5/5]${C_WHITE} Generando atajos de terminal en ${C_GRAY}~/.local/bin${C_RESET}..."
    create_cli_shortcuts
    print_centered "      ${C_GREEN}✓${C_WHITE} Atajos configurados con permisos de ejecución.${C_RESET}"
    print_centered ""

    # 6. Verificación Post-Instalación (Smoke Test)
    print_centered "${C_WHITE}Ejecutando prueba de verificación rápida de librerías...${C_RESET}"
    local smoke_test
    smoke_test=$("${VENV_DIR}/bin/python" -c "
import cv2, mediapipe, sklearn, PIL, numpy
print('OK')
" 2>/dev/null || echo "FAIL")

    if [ "$smoke_test" != "OK" ]; then
        print_centered "      ${C_YELLOW}⚠ Advertencia: El test de importación arrojó observaciones.${C_RESET}"
        print_centered "      ${C_GRAY}Revise el registro en ${LOG_FILE}${C_RESET}"
    else
        print_centered "      ${C_GREEN}✓${C_WHITE} Todas las librerías clave importadas correctamente.${C_RESET}"
    fi
    print_centered ""

    # Resumen de instalación
    print_box_top
    print_box_row "${C_GREEN}${C_BOLD}¡INSTALACIÓN COMPLETADA CON ÉXITO!${C_RESET}" "center"
    print_box_sep
    print_box_row "${C_WHITE}Ya puede invocar HandTalk directamente desde cualquier terminal:${C_RESET}" "center"
    print_box_row "" "center"
    print_box_row "${C_CYAN}  1. handtalk-captura   ${C_GRAY}→ Captura y recolección de señas${C_RESET}" "left_tight"
    print_box_row "${C_CYAN}  2. handtalk-entrenar  ${C_GRAY}→ Entrenamiento del clasificador${C_RESET}" "left_tight"
    print_box_row "${C_CYAN}  3. handtalk-traducir  ${C_GRAY}→ Traducción en tiempo real (cámara)${C_RESET}" "left_tight"
    print_box_row "" "center"
    print_box_row "${C_GRAY}Nota: Si abre una terminal nueva y no detecta los comandos,${C_RESET}" "center"
    print_box_row "${C_GRAY}ejecute: source ~/.bashrc (o reinicie la sesión de consola).${C_RESET}" "center"
    print_box_bottom

    wait_enter
}

# --- Acción 2: Actualización de Dependencias ---

do_update_dependencies() {
    print_header_banner
    print_box_top
    print_box_row "${C_CYAN}${C_BOLD}ACTUALIZACIÓN DE DEPENDENCIAS (VIRTUALENV)${C_RESET}" "center"
    print_box_bottom
    print_centered ""

    # 1. Validación de Pre-requisito: Entorno virtual
    if [ ! -d "${VENV_DIR}" ] || [ ! -f "${VENV_DIR}/bin/python" ] || [ ! -f "${VENV_DIR}/bin/pip" ]; then
        print_box_top
        print_box_row "${C_RED}✗ ERROR: ENTORNO VIRTUAL NO ENCONTRADO${C_RESET}" "center"
        print_box_sep
        print_box_row "${C_WHITE}No se detectó un entorno virtual válido en ./venv.${C_RESET}" "center"
        print_box_row "${C_YELLOW}No se pueden actualizar dependencias sin un entorno previo.${C_RESET}" "center"
        print_box_row "" "center"
        print_box_row "${C_CYAN}Solución recomendada:${C_RESET}" "left"
        print_box_row "  • Ejecute primero la opción [1] (Instalación Completa)." "left_tight"
        print_box_bottom
        wait_enter
        return 1
    fi

    # 2. Validación de Pre-requisito: Atajos CLI
    local shortcuts=("handtalk-captura" "handtalk-entrenar" "handtalk-traducir")
    local missing_shortcuts=0
    for name in "${shortcuts[@]}"; do
        if [ ! -f "${BIN_DIR}/${name}" ]; then
            missing_shortcuts=1
            break
        fi
    done

    if [ "$missing_shortcuts" -eq 1 ]; then
        print_box_top
        print_box_row "${C_RED}✗ ERROR: ATAJOS CLI NO ENCONTRADOS${C_RESET}" "center"
        print_box_sep
        print_box_row "${C_WHITE}No se encontraron los atajos globales en ~/.local/bin.${C_RESET}" "center"
        print_box_row "${C_YELLOW}El sistema requiere que la instalación inicial esté completa.${C_RESET}" "center"
        print_box_row "" "center"
        print_box_row "${C_CYAN}Solución recomendada:${C_RESET}" "left"
        print_box_row "  • Ejecute primero la opción [1] (Instalación Completa)." "left_tight"
        print_box_bottom
        wait_enter
        return 1
    fi

    # 3. Validación de Pre-requisito: Archivo requirements.txt
    if [ ! -f "${REQUIREMENTS_FILE}" ]; then
        print_box_top
        print_box_row "${C_RED}✗ ERROR: ARCHIVO DE REQUERIMIENTOS NO ENCONTRADO${C_RESET}" "center"
        print_box_sep
        print_box_row "${C_WHITE}No se encontró el archivo inicio/requirements.txt.${C_RESET}" "center"
        print_box_bottom
        wait_enter
        return 1
    fi

    # Ejecución de la actualización
    print_centered "${C_CYAN}[1/3]${C_WHITE} Validando entorno virtual y atajos CLI...${C_RESET}"
    print_centered "      ${C_GREEN}✓${C_WHITE} Entorno virtual y atajos detectados correctamente.${C_RESET}"
    print_centered ""

    print_centered "${C_CYAN}[2/3]${C_WHITE} Sincronizando dependencias desde ${C_GRAY}inicio/requirements.txt${C_RESET}..."
    print_centered "      ${C_GRAY}(Solo se instalarán paquetes nuevos o pendientes)${C_RESET}"

    if ! "${VENV_DIR}/bin/pip" install -r "${REQUIREMENTS_FILE}" >>"${LOG_FILE}" 2>&1; then
        print_centered ""
        print_box_top
        print_box_row "${C_RED}✗ ERROR AL ACTUALIZAR DEPENDENCIAS${C_RESET}" "center"
        print_box_sep
        print_box_row "${C_WHITE}Hubo un problema al instalar las nuevas librerías.${C_RESET}" "center"
        print_box_row "${C_GRAY}Consulte los detalles en el archivo de registro:${C_RESET}" "center"
        print_box_row "${C_YELLOW}${LOG_FILE}${C_RESET}" "center"
        print_box_bottom
        wait_enter
        return 1
    fi
    print_centered "      ${C_GREEN}✓${C_WHITE} Dependencias instaladas y actualizadas.${C_RESET}"
    print_centered ""

    print_centered "${C_CYAN}[3/3]${C_WHITE} Verificando integridad del entorno virtual...${C_RESET}"
    local smoke_test
    smoke_test=$("${VENV_DIR}/bin/python" -c "
import cv2, mediapipe, sklearn, PIL, numpy
print('OK')
" 2>/dev/null || echo "FAIL")

    if [ "$smoke_test" != "OK" ]; then
        print_centered "      ${C_YELLOW}⚠ Advertencia: El test de importación arrojó observaciones.${C_RESET}"
        print_centered "      ${C_GRAY}Revise el registro en ${LOG_FILE}${C_RESET}"
    else
        print_centered "      ${C_GREEN}✓${C_WHITE} Todas las librerías clave importadas correctamente.${C_RESET}"
    fi
    print_centered ""

    # Resumen de éxito
    print_box_top
    print_box_row "${C_GREEN}${C_BOLD}¡DEPENDENCIAS ACTUALIZADAS CON ÉXITO!${C_RESET}" "center"
    print_box_sep
    print_box_row "${C_WHITE}El entorno virtual ahora cuenta con todas las librerías${C_RESET}" "center"
    print_box_row "${C_WHITE}especificadas en inicio/requirements.txt.${C_RESET}" "center"
    print_box_row "" "center"
    print_box_row "${C_GRAY}Sus atajos y modelos continúan listos para usar.${C_RESET}" "center"
    print_box_bottom

    wait_enter
}

# --- Acción 3: Desinstalación ---

do_uninstallation() {
    print_header_banner
    print_box_top
    print_box_row "${C_YELLOW}${C_BOLD}DESINSTALACIÓN DE HANDTALK${C_RESET}" "center"
    print_box_sep
    print_box_row "${C_WHITE}Esta acción eliminará el entorno virtual (./venv)${C_RESET}" "center"
    print_box_row "${C_WHITE}y los atajos creados en ~/.local/bin.${C_RESET}" "center"
    print_box_bottom
    print_centered ""

    prompt_centered "${C_RED}¿Está seguro de que desea desinstalar HandTalk? [s/N]: ${C_RESET}"
    # shellcheck disable=SC2162
    read -r confirm
    if [[ ! "$confirm" =~ ^[sS]$ ]]; then
        print_centered ""
        print_centered "${C_YELLOW}Operación cancelada. No se realizaron cambios.${C_RESET}"
        wait_enter
        return 0
    fi

    print_centered ""
    print_centered "${C_CYAN}[1/3]${C_WHITE} Eliminando entorno virtual ./venv...${C_RESET}"
    if [ -d "${VENV_DIR}" ]; then
        rm -rf "${VENV_DIR}"
        print_centered "      ${C_GREEN}✓${C_WHITE} Entorno virtual eliminado.${C_RESET}"
    else
        print_centered "      ${C_GRAY}ℹ No se encontró carpeta venv/.${C_RESET}"
    fi

    print_centered "${C_CYAN}[2/3]${C_WHITE} Eliminando atajos de terminal en ~/.local/bin...${C_RESET}"
    remove_cli_shortcuts
    print_centered "      ${C_GREEN}✓${C_WHITE} Atajos eliminados.${C_RESET}"

    print_centered "${C_CYAN}[3/3]${C_WHITE} Limpiando configuraciones de PATH del sistema...${C_RESET}"
    print_centered "      ${C_GREEN}✓${C_WHITE} Archivos rc limpiados.${C_RESET}"
    print_centered ""

    print_box_top
    print_box_row "${C_GREEN}${C_BOLD}DESINSTALACIÓN COMPLETADA${C_RESET}" "center"
    print_box_sep
    print_box_row "${C_WHITE}Todos los componentes generados han sido retirados.${C_RESET}" "center"
    print_box_row "${C_GRAY}Sus datos y modelos entrenados se mantienen intactos.${C_RESET}" "center"
    print_box_bottom

    wait_enter
}

# --- Bucle Principal del Menú ---

main() {
    while true; do
        print_header_banner
        print_menu
        prompt_centered "${C_CYAN}${C_BOLD}Seleccione una opción [1-4]: ${C_RESET}"
        # shellcheck disable=SC2162
        read -r choice

        case "$choice" in
            1)
                do_installation
                ;;
            2)
                do_update_dependencies
                ;;
            3)
                do_uninstallation
                ;;
            4)
                print_header_banner
                print_box_top
                print_box_row "${C_WHITE}¡GRACIAS POR USAR HANDTALK!${C_RESET}" "center"
                print_box_sep
                print_box_row "${C_GRAY}Lenguaje de Señas Potenciado con Visión e IA${C_RESET}" "center"
                print_box_bottom
                print_centered ""
                exit 0
                ;;
            *)
                print_centered ""
                print_centered "${C_RED}Opción no válida. Ingrese 1, 2, 3 o 4.${C_RESET}"
                sleep 1.2
                ;;
        esac
    done
}

main "$@"
