#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_manager.py

Módulo de importación y exportación de paquetes HandTalk.

Un paquete HandTalk es un archivo .zip que contiene:
  - manifest.json         -> ficha técnica del paquete (autogenerado)
  - README.txt            -> descripción legible para humanos (autogenerado)
  - dataset/              -> todos los .json de muestras
  - models/               -> custom_sign_model.pkl + labels + meta (opcional)

Modos de importación:
  - REEMPLAZAR: borra dataset y modelo locales, pone los del paquete.
                Ideal para máquina nueva o reset.
  - FUSIONAR:   añade muestras del paquete al dataset local, respetando
                decisiones por palabra en conflictos. NO importa modelo
                (porque el modelo local queda desactualizado y hay que
                reentrenar).

Autor: equipo HandTalk.
"""

import os
import json
import glob
import zipfile
import shutil
from datetime import datetime
from typing import Optional

PACK_FORMAT = "handtalk_dataset_pack"
PACK_VERSION = "1.0.0"
HANDTALK_VERSION = "1.0.0"

# Nombres esperados de los archivos del modelo
MODEL_FILES = [
    "custom_sign_model.pkl",
    "custom_sign_labels.pkl",
    "custom_sign_meta.json",
]

# Modos de importación
MODE_REEMPLAZAR = "reemplazar"
MODE_FUSIONAR = "fusionar"

# Decisiones por conflicto
DEC_FUSIONAR = "fusionar"
DEC_REEMPLAZAR = "reemplazar"
DEC_OMITIR = "omitir"
DEC_RENOMBRAR = "renombrar"  # se acompaña de nuevo nombre: "renombrar:xxx"


# ============================================================================
# UTILIDADES INTERNAS
# ============================================================================

def _ahora_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _leer_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _escribir_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _siguiente_indice(dataset_dir: str, label: str, sample_type: str = "static") -> int:
    """
    Devuelve el siguiente índice libre para esa palabra+tipo.
    Respeta el naming: <label>_<idx>_<type>.json
    """
    max_i = -1
    patron = os.path.join(dataset_dir, f"{label}_*_{sample_type}.json")
    for path in glob.glob(patron):
        fname = os.path.basename(path)
        # <label>_<idx>_<type>.json -> nos interesa el idx
        base = fname.replace(f"_{sample_type}.json", "")
        partes = base.split("_")
        # label puede tener "_" internos, el último es el idx
        try:
            idx = int(partes[-1])
            max_i = max(max_i, idx)
        except (ValueError, IndexError):
            continue
    return max_i + 1


def _contar_por_palabra(dataset_dir: str) -> dict:
    """
    Devuelve {palabra: cantidad_muestras} leyendo los .json del dataset.
    """
    conteo = {}
    if not os.path.isdir(dataset_dir):
        return conteo
    for path in glob.glob(os.path.join(dataset_dir, "*.json")):
        try:
            data = _leer_json(path)
            label = data.get("label", "")
            if label:
                conteo[label] = conteo.get(label, 0) + 1
        except Exception:
            continue
    return conteo


def _borrar_palabra(dataset_dir: str, label: str):
    """Borra todos los .json de una palabra local."""
    for path in glob.glob(os.path.join(dataset_dir, f"{label}_*.json")):
        try:
            os.remove(path)
        except Exception:
            pass


def _backup_modelo(models_dir: str) -> Optional[str]:
    """
    Renombra los archivos del modelo actual a .bak_<timestamp> para no
    perderlos. Devuelve la carpeta de backup o None si no había modelo.
    """
    if not os.path.isdir(models_dir):
        return None

    existentes = [f for f in MODEL_FILES if os.path.exists(os.path.join(models_dir, f))]
    if not existentes:
        return None

    backup_name = f"backup_{_ahora_str()}"
    backup_dir = os.path.join(models_dir, backup_name)
    os.makedirs(backup_dir, exist_ok=True)

    for fname in existentes:
        try:
            shutil.move(
                os.path.join(models_dir, fname),
                os.path.join(backup_dir, fname)
            )
        except Exception:
            pass

    return backup_dir


# ============================================================================
# EXPORTAR
# ============================================================================

def exportar_paquete(
    destino_zip: str,
    dataset_dir: str,
    models_dir: str,
    autor: str = "Anónimo",
    descripcion: str = "",
    incluir_dataset: bool = True,
    incluir_modelo: bool = True,
) -> dict:
    """
    Empaqueta dataset + modelo en un .zip portable con manifest autogenerado.

    Retorna el manifest generado.
    """
    manifest = {
        "formato": PACK_FORMAT,
        "pack_version": PACK_VERSION,
        "handtalk_version": HANDTALK_VERSION,
        "fecha_creacion": datetime.now().isoformat(),
        "autor": autor,
        "descripcion": descripcion,
        "num_features": None,
        "palabras": {},
        "total_muestras": 0,
        "modelo_incluido": False,
        "model_type": None,
        "words": [],
    }

    # Asegurar carpeta destino
    os.makedirs(os.path.dirname(os.path.abspath(destino_zip)), exist_ok=True)

    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as zf:

        # --------------------------------------------------------------
        # 1. DATASET
        # --------------------------------------------------------------
        if incluir_dataset and os.path.isdir(dataset_dir):
            conteo = {}
            for path in glob.glob(os.path.join(dataset_dir, "*.json")):
                try:
                    data = _leer_json(path)
                except Exception:
                    continue
                label = data.get("label", "")
                if not label:
                    continue
                fname = os.path.basename(path)
                zf.write(path, arcname=f"dataset/{fname}")
                conteo[label] = conteo.get(label, 0) + 1

            manifest["palabras"] = conteo
            manifest["total_muestras"] = sum(conteo.values())
            manifest["words"] = sorted(conteo.keys())

        # --------------------------------------------------------------
        # 2. MODELO
        # --------------------------------------------------------------
        if incluir_modelo and os.path.isdir(models_dir):
            # Leer meta primero para sacar info
            meta_path = os.path.join(models_dir, "custom_sign_meta.json")
            if os.path.exists(meta_path):
                try:
                    meta = _leer_json(meta_path)
                    manifest["model_type"] = meta.get("model_type")
                    manifest["num_features"] = meta.get("feature_length")
                    manifest["words"] = meta.get("words", manifest["words"])
                except Exception:
                    pass

            # Empaquetar los archivos del modelo
            modelo_ok = False
            for fname in MODEL_FILES:
                fpath = os.path.join(models_dir, fname)
                if os.path.exists(fpath):
                    zf.write(fpath, arcname=f"models/{fname}")
                    if fname == "custom_sign_model.pkl":
                        modelo_ok = True

            manifest["modelo_incluido"] = modelo_ok

        # --------------------------------------------------------------
        # 3. README
        # --------------------------------------------------------------
        zf.writestr("README.txt", _generar_readme(manifest))

        # --------------------------------------------------------------
        # 4. MANIFEST (al final, ya completo)
        # --------------------------------------------------------------
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )

    return manifest


def _generar_readme(manifest: dict) -> str:
    palabras = manifest.get("palabras", {})
    lista_palabras = "\n".join(
        f"  - {w}: {c} muestras" for w, c in sorted(palabras.items())
    ) or "  (sin palabras)"

    return f"""HandTalk — Paquete de Dataset y Modelo
=======================================

Formato:       {manifest.get('formato')}
Versión pack:  {manifest.get('pack_version')}
Versión app:   {manifest.get('handtalk_version')}
Fecha:         {manifest.get('fecha_creacion')}
Autor:         {manifest.get('autor')}
Descripción:   {manifest.get('descripcion') or '(sin descripción)'}

Contenido:
{lista_palabras}

Total de muestras: {manifest.get('total_muestras', 0)}
Modelo incluido:   {'Sí' if manifest.get('modelo_incluido') else 'No'}
Tipo de modelo:    {manifest.get('model_type') or '—'}
Nº features:       {manifest.get('num_features') or '—'}

---------------------------------------
Para importar este paquete:
  1. Abre HandTalk
  2. Ve a "Importar / Exportar"
  3. Selecciona este archivo .zip
  4. Elige el modo de importación

Generado automáticamente por HandTalk.
"""


# ============================================================================
# LEER MANIFEST (sin descomprimir todo)
# ============================================================================

def leer_manifest(ruta_zip: str) -> dict:
    """
    Lee SOLO el manifest.json del .zip. Rápido.
    Lanza excepción si el archivo no es un paquete válido.
    """
    if not zipfile.is_zipfile(ruta_zip):
        raise ValueError("El archivo no es un .zip válido.")

    with zipfile.ZipFile(ruta_zip, "r") as zf:
        nombres = zf.namelist()
        if "manifest.json" not in nombres:
            raise ValueError(
                "El .zip no contiene manifest.json. "
                "¿Es realmente un paquete HandTalk?"
            )
        with zf.open("manifest.json") as f:
            manifest = json.load(f)

    if manifest.get("formato") != PACK_FORMAT:
        raise ValueError(
            f"Formato desconocido: {manifest.get('formato')}. "
            f"Se esperaba '{PACK_FORMAT}'."
        )

    return manifest


# ============================================================================
# DETECTAR CONFLICTOS
# ============================================================================

def detectar_conflictos(ruta_zip: str, dataset_dir: str) -> dict:
    """
    Compara el manifest del paquete con el dataset local.

    Retorna dict con:
      - manifest: el manifest leído
      - palabras_locales: {palabra: cantidad} local
      - palabras_paquete: {palabra: cantidad} del paquete
      - solo_local: palabras que solo están local
      - solo_paquete: palabras nuevas que trae el paquete
      - conflictos: {palabra: {"local": n, "paquete": m}}
      - compatible_features: True/False (si num_features coincide)
      - features_local: nº features detectado en local (si se puede)
    """
    manifest = leer_manifest(ruta_zip)

    palabras_locales = _contar_por_palabra(dataset_dir)
    palabras_paquete = manifest.get("palabras", {})

    solo_local = sorted(set(palabras_locales) - set(palabras_paquete))
    solo_paquete = sorted(set(palabras_paquete) - set(palabras_locales))

    conflictos = {}
    for palabra in set(palabras_locales) & set(palabras_paquete):
        conflictos[palabra] = {
            "local": palabras_locales[palabra],
            "paquete": palabras_paquete[palabra],
        }

    # Comparar nº de features
    features_paquete = manifest.get("num_features")
    features_local = _detectar_features_local(dataset_dir)
    compatible = True
    if features_paquete and features_local and features_paquete != features_local:
        compatible = False

    return {
        "manifest": manifest,
        "palabras_locales": palabras_locales,
        "palabras_paquete": palabras_paquete,
        "solo_local": solo_local,
        "solo_paquete": solo_paquete,
        "conflictos": conflictos,
        "compatible_features": compatible,
        "features_local": features_local,
        "features_paquete": features_paquete,
    }


def _detectar_features_local(dataset_dir: str) -> Optional[int]:
    """Lee el primer .json del dataset y saca el tamaño del vector."""
    if not os.path.isdir(dataset_dir):
        return None
    archivos = glob.glob(os.path.join(dataset_dir, "*.json"))
    if not archivos:
        return None
    try:
        data = _leer_json(archivos[0])
        feats = data.get("features")
        if isinstance(feats, list) and feats:
            if isinstance(feats[0], list):
                return len(feats[0])  # dinámico -> largo de un frame
            return len(feats)         # estático
    except Exception:
        pass
    return None


# ============================================================================
# IMPORTAR
# ============================================================================

def importar_paquete(
    ruta_zip: str,
    dataset_dir: str,
    models_dir: str,
    modo: str,
    decisiones: Optional[dict] = None,
    importar_modelo: bool = False,
) -> dict:
    """
    Aplica la importación.

    Parámetros:
      - modo: MODE_REEMPLAZAR o MODE_FUSIONAR
      - decisiones: solo se usa en FUSIONAR.
          {palabra: "fusionar" | "reemplazar" | "omitir" | "renombrar:nuevo"}
      - importar_modelo: solo válido en REEMPLAZAR. En FUSIONAR se ignora
        (el modelo local se respalda y se pide reentrenar).

    Retorna un reporte con lo que pasó.
    """
    decisiones = decisiones or {}
    reporte = {
        "modo": modo,
        "palabras_anadidas": [],
        "palabras_fusionadas": [],
        "palabras_reemplazadas": [],
        "palabras_omitidas": [],
        "palabras_renombradas": [],
        "total_muestras_importadas": 0,
        "modelo_importado": False,
        "modelo_respaldado": None,
        "advertencias": [],
    }

    manifest = leer_manifest(ruta_zip)
    os.makedirs(dataset_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # MODO REEMPLAZAR
    # ------------------------------------------------------------------
    if modo == MODE_REEMPLAZAR:
        # 1. Respaldar modelo actual si existe
        backup = _backup_modelo(models_dir)
        if backup:
            reporte["modelo_respaldado"] = backup

        # 2. Borrar dataset local completo
        for path in glob.glob(os.path.join(dataset_dir, "*.json")):
            try:
                os.remove(path)
            except Exception:
                pass

        # 3. Extraer dataset del paquete
        with zipfile.ZipFile(ruta_zip, "r") as zf:
            for nombre in zf.namelist():
                if nombre.startswith("dataset/") and nombre.endswith(".json"):
                    fname = os.path.basename(nombre)
                    data = zf.read(nombre)
                    with open(os.path.join(dataset_dir, fname), "wb") as f:
                        f.write(data)
                    reporte["total_muestras_importadas"] += 1

            # 4. Extraer modelo si se pidió
            if importar_modelo and manifest.get("modelo_incluido"):
                os.makedirs(models_dir, exist_ok=True)
                modelo_ok = False
                for fname in MODEL_FILES:
                    arc = f"models/{fname}"
                    if arc in zf.namelist():
                        data = zf.read(arc)
                        with open(os.path.join(models_dir, fname), "wb") as f:
                            f.write(data)
                        if fname == "custom_sign_model.pkl":
                            modelo_ok = True
                reporte["modelo_importado"] = modelo_ok

        # Reporte de palabras
        reporte["palabras_anadidas"] = sorted(manifest.get("palabras", {}).keys())
        return reporte

    # ------------------------------------------------------------------
    # MODO FUSIONAR
    # ------------------------------------------------------------------
    if modo == MODE_FUSIONAR:
        # 1. Respaldar modelo actual (porque el dataset va a cambiar)
        backup = _backup_modelo(models_dir)
        if backup:
            reporte["modelo_respaldado"] = backup
            reporte["advertencias"].append(
                "Se respaldó el modelo anterior. Debes reentrenar tras importar."
            )

        # 2. Aplicar decisiones por palabra
        with zipfile.ZipFile(ruta_zip, "r") as zf:
            for nombre in zf.namelist():
                if not (nombre.startswith("dataset/") and nombre.endswith(".json")):
                    continue
                try:
                    data = json.loads(zf.read(nombre).decode("utf-8"))
                except Exception:
                    continue

                label_orig = data.get("label", "")
                if not label_orig:
                    continue

                decision = decisiones.get(label_orig, DEC_FUSIONAR)

                # Omitir
                if decision == DEC_OMITIR:
                    if label_orig not in reporte["palabras_omitidas"]:
                        reporte["palabras_omitidas"].append(label_orig)
                    continue

                # Renombrar
                if decision.startswith(DEC_RENOMBRAR + ":"):
                    nuevo = decision.split(":", 1)[1].strip()
                    if nuevo:
                        data["label"] = nuevo
                        if f"{label_orig} -> {nuevo}" not in reporte["palabras_renombradas"]:
                            reporte["palabras_renombradas"].append(
                                f"{label_orig} -> {nuevo}"
                            )
                        label_final = nuevo
                    else:
                        label_final = label_orig
                else:
                    label_final = label_orig

                # Reemplazar: borrar todos los locales de esta palabra primero
                if decision == DEC_REEMPLAZAR:
                    _borrar_palabra(dataset_dir, label_final)
                    if label_final not in reporte["palabras_reemplazadas"]:
                        reporte["palabras_reemplazadas"].append(label_final)

                # Fusionar: solo registramos
                if decision == DEC_FUSIONAR:
                    if label_final not in reporte["palabras_fusionadas"]:
                        reporte["palabras_fusionadas"].append(label_final)

                # Escribir con índice nuevo
                sample_type = data.get("type", "static")
                idx = _siguiente_indice(dataset_dir, label_final, sample_type)
                fname_out = f"{label_final}_{idx}_{sample_type}.json"
                _escribir_json(os.path.join(dataset_dir, fname_out), data)
                reporte["total_muestras_importadas"] += 1

        # 3. Palabras nuevas (sin conflicto)
        conteo_actual = _contar_por_palabra(dataset_dir)
        for palabra in manifest.get("palabras", {}):
            # Fueron conflicto? No lo sabemos aquí directo, así que
            # simplemente marcamos las que no están en las otras listas
            if (palabra not in reporte["palabras_fusionadas"]
                    and palabra not in reporte["palabras_reemplazadas"]
                    and palabra not in reporte["palabras_omitidas"]
                    and not any(palabra in r for r in reporte["palabras_renombradas"])):
                if palabra not in reporte["palabras_anadidas"]:
                    reporte["palabras_anadidas"].append(palabra)

        return reporte

    raise ValueError(f"Modo desconocido: {modo}")


# ============================================================================
# ESTADO ACTUAL (para mostrar en la pestaña "datos")
# ============================================================================

def estado_actual(dataset_dir: str, models_dir: str) -> dict:
    """
    Devuelve info resumida del estado local para mostrar en la UI.
    """
    palabras = _contar_por_palabra(dataset_dir)
    total_muestras = sum(palabras.values())

    modelo_file = os.path.join(models_dir, "custom_sign_model.pkl")
    meta_file = os.path.join(models_dir, "custom_sign_meta.json")

    modelo_ok = os.path.exists(modelo_file) and os.path.exists(meta_file)
    model_type = None
    model_words = []
    if modelo_ok:
        try:
            meta = _leer_json(meta_file)
            model_type = meta.get("model_type")
            model_words = meta.get("words", [])
        except Exception:
            pass

    return {
        "palabras": palabras,
        "total_palabras": len(palabras),
        "total_muestras": total_muestras,
        "modelo_ok": modelo_ok,
        "model_type": model_type,
        "model_words": model_words,
        "dataset_dir": dataset_dir,
        "models_dir": models_dir,
    }
