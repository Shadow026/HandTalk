#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realtime_translator.py

REEMPLAZA a translator_realtime.py, translator_unified.py y
translator_headless.py, unificando su logica en un solo traductor que
funciona con CUALQUIER conjunto de palabras que el usuario haya definido
(ya no hay "digitos" ni "letras" hardcodeados).

RESCATADO de los traductores originales:
  - Apertura de camara con fallback (ahora en camera_utils.open_camera)
  - Deteccion de manos con MediaPipe y umbrales altos de confianza
    (0.85 deteccion / 0.75 tracking) para evitar falsos positivos
  - Dibujo de landmarks y bounding box
  - Sistema de confirmacion por frames consecutivos (ahora en smoothing.py)

NUEVO (señas dinámicas):
  - Carga TAMBIEN el modelo dinamico (custom_sign_model_dinamico.pkl) si
    existe, de forma opcional/graceful: si no esta entrenado todavia, el
    traductor sigue funcionando solo con senas estaticas, sin romperse.
    
  - Detector de movimiento basado en la posicion CRUDA de la muñeca (no
    en el vector normalizado de hand_features.py, que es invariante a
    rotacion/escala para que el modelo estatico funcione sin importar el
    angulo de la mano -- pero esa misma invariancia hace que un
    movimiento como agitar la mano, que es basicamente una rotacion de
    la muñeca, casi no cambie el vector normalizado entre frames).
    
  - SEGMENTACION POR EVENTO DE MOVIMIENTO: en vez de una ventana de
    tamaño fijo (que mezclaba el final del gesto con frames de mano
    quieta, o el inicio de otro gesto), se detecta el evento completo:
    se empieza a grabar cuando la mano se mueve, y se predice UNA SOLA
    VEZ con toda la secuencia real cuando el movimiento termina (mano
    quieta varios frames seguidos, o mano perdida). Esto evita diluir la
    señal de desviación/delta que usa temporal_pooling.pool_sequence()
    con datos que no son parte real del gesto.
    
  - MARGEN DE CONFIANZA: no basta con que la palabra top-1 supere el
    umbral de confianza; también debe superarle por un margen mínimo a
    la segunda opción más probable, para no confirmar cuando el modelo
    está prácticamente indeciso entre dos señas parecidas.
    
  - MODOS DE OPERACION (--modo): "ambos" (normal), "estatico" o
    "dinamico" puros, útiles para probar cada parte por separado sin que
    la otra interfiera (por ejemplo, para medir rendimiento o precisión
    de forma aislada).
    
  - ARBITRO (modo="ambos"): en cada frame solo se evalua UN modelo, nunca
    los dos a la vez -- si hay un gesto dinamico en curso, el estatico se
    pone en pausa (no acumula progreso de confirmacion), y viceversa.
    Esto evita que el estatico confirme por error una postura intermedia
    de un movimiento como si fuera una seña fija.
    
  - Downscale opcional antes de MediaPipe (--input-size) para aliviar
    carga de procesamiento en camaras de alta resolucion.
"""
"""
Modos de ejecucion disponibles (utiles para pruebas aisladas):

    python realtime_translator.py --modo ambos      # estatico + dinamico (normal)
    python realtime_translator.py --modo estatico   # solo modelo estatico
    python realtime_translator.py --modo dinamico   # solo modelo dinamico
"""

import argparse
import json
import os
import time
from collections import deque

import cv2
import mediapipe as mp
import joblib

import camera_utils
import hand_features
from smoothing import PredictionSmoother
from temporal_pooling import pool_sequence

MODELS_DIR = "./models"
NOMBRE_VENTANA = "Traductor de Senas Personalizado"

# No hace falta esperar el gesto completo para dar una primera
# estimacion en pantalla -- pool_sequence funciona igual de bien con
# pocos frames que con muchos, así que se puede mostrar un preview
# apenas hay un mínimo razonable de datos.
MINIMO_FRAMES_PARA_PREDECIR = 5

MODOS_VALIDOS = ("ambos", "estatico", "dinamico")

# Tope de seguridad: si por algún motivo el detector de movimiento se
# queda "pegado" en True (ruido, iluminación, etc.), esto evita que el
# buffer crezca indefinidamente sin nunca cerrar el gesto.
MAX_FRAMES_GESTO = 45

# Cuantos frames SEGUIDOS sin movimiento hacen falta para considerar que
# el gesto ya terminó. Mas alto = mas tolerante a micro-pausas dentro de
# un mismo gesto, pero tambien mas lento para confirmar.
FRAMES_QUIETO_PARA_FINALIZAR = 4

# Diferencia mínima requerida entre la probabilidad de la palabra más
# probable (top-1) y la segunda más probable (top-2) para aceptar la
# confirmación. Evita confirmar cuando el modelo esta practicamente
# empatado entre dos señas parecidas.
MARGEN_CONFIANZA_MINIMO = 0.12

# Mientras el gesto sigue en curso, no hace falta correr predict_proba
# en cada frame solo para actualizar el preview en pantalla -- se
# throttlea a 1 de cada N frames para ahorrar computo sin que se note.
CADA_N_FRAMES_PREVIEW = 2


class CustomSignTranslator:
    def __init__(self, models_dir=MODELS_DIR, max_hands=1, rotate_invariant=True,
                 confidence_threshold=0.75, confidence_threshold_dinamico=0.65,
                 umbral_movimiento=0.015, modo="ambos", input_size=480,
                 margen_confianza=MARGEN_CONFIANZA_MINIMO,
                 frames_quieto_para_finalizar=FRAMES_QUIETO_PARA_FINALIZAR):

        if modo not in MODOS_VALIDOS:
            raise ValueError(f"modo invalido: {modo}. Usa uno de {MODOS_VALIDOS}")

        self.modo = modo
        self.input_size = input_size
        self.max_hands = max_hands
        self.rotate_invariant = rotate_invariant
        self.history = []
        self.margen_confianza = margen_confianza
        self.frames_quieto_para_finalizar = frames_quieto_para_finalizar

        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=0.85,
            min_tracking_confidence=0.75,
        )

        # --- Modelo estatico: se carga solo si el modo lo requiere, para
        # poder probar "modo=dinamico" sin necesitar un modelo estatico
        # entrenado en absoluto. ---
        self.model = None
        self.encoder = None
        self.meta = None
        self.smoother = None

        if modo in ("ambos", "estatico"):
            model_path = os.path.join(models_dir, "custom_sign_model.pkl")
            encoder_path = os.path.join(models_dir, "custom_sign_labels.pkl")
            meta_path = os.path.join(models_dir, "custom_sign_meta.json")
            for p in (model_path, encoder_path, meta_path):
                if not os.path.exists(p):
                    raise FileNotFoundError(
                        f"[modo={modo}] No se encontro {p}. Entrena el modelo estatico."
                    )
            self.model = joblib.load(model_path)
            self.encoder = joblib.load(encoder_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                self.meta = json.load(f)
            self.smoother = PredictionSmoother(confidence_threshold=confidence_threshold)
            print(f"[OK] Modelo ESTATICO cargado. Senas: {self.meta.get('words', [])}")
        else:
            print("[INFO] modo=dinamico: modelo estatico NO cargado")

        # --- Modelo dinamico: carga OPCIONAL/graceful -- si no existe
        # (aun no se ha entrenado), el traductor sigue funcionando solo
        # con senas estaticas sin romperse. ---
        self.modelo_dinamico = None
        self.encoder_dinamico = None
        self.meta_dinamico = None
        self.confidence_threshold_dinamico = confidence_threshold_dinamico

        # El deque tiene un maxlen de SEGURIDAD (MAX_FRAMES_GESTO), pero
        # ya no representa una "ventana objetivo" fija -- el largo real
        # de cada gesto lo decide cuándo empieza y termina el movimiento
        # (ver _procesar_segmentacion).
        self.buffer_dinamico = deque(maxlen=MAX_FRAMES_GESTO)

        if modo in ("ambos", "dinamico"):
            self._cargar_modelo_dinamico(models_dir)
        else:
            print("[INFO] modo=estatico: modelo dinamico NO cargado")

        # --- Detector de movimiento: posicion CRUDA de la muñeca en la
        # imagen (x, y), no el vector normalizado de hand_features.py. ---
        self.wrist_anterior = None
        self.umbral_movimiento = umbral_movimiento

        # --- Estado de la maquina de segmentación por evento ---
        self.grabando_gesto = False
        self.frames_quieto_en_gesto = 0
        self._frame_idx = 0
        self._ultimo_dinamico = (None, 0.0, None, 0.0)  # cache del ultimo preview mostrado

    def _cargar_modelo_dinamico(self, models_dir):
        """Carga el modelo dinamico si existe. Si no, el traductor sigue
        funcionando solo con senas estaticas (no se rompe nada)."""
        model_path = os.path.join(models_dir, "custom_sign_model_dinamico.pkl")
        encoder_path = os.path.join(models_dir, "custom_sign_labels_dinamico.pkl")
        meta_path = os.path.join(models_dir, "custom_sign_meta_dinamico.json")
        if not all(os.path.exists(p) for p in (model_path, encoder_path, meta_path)):
            print("[AVISO] Modelo dinamico no encontrado. Solo senas estaticas.")
            return
        self.modelo_dinamico = joblib.load(model_path)
        self.encoder_dinamico = joblib.load(encoder_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta_dinamico = json.load(f)
        print(f"[OK] Modelo DINAMICO cargado. Senas: {self.meta_dinamico.get('words', [])}")

    def _procesar_mediapipe(self, frame):
        """Reduce el tamaño del frame (si aplica) antes de pasarlo a
        MediaPipe, para aliviar carga de procesamiento en camaras de
        alta resolucion sin perder precision de deteccion relevante."""
        h, w = frame.shape[:2]
        scale = 1.0
        if self.input_size and max(h, w) > self.input_size:
            scale = self.input_size / max(h, w)
            small = cv2.resize(frame, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_LINEAR)
        else:
            small = frame
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.hands.process(rgb)
        return results, small

    def _medir_movimiento(self, results):
        """Calcula el desplazamiento de la muñeca respecto al frame
        anterior. Se usa la posicion CRUDA (no normalizada) porque el
        vector de hand_features.py es invariante a rotacion, y por eso
        "no nota" un simple agitar de mano."""
        if not results.multi_hand_landmarks:
            self.wrist_anterior = None
            return False, 0.0
        wrist_lm = results.multi_hand_landmarks[0].landmark[0]
        wrist_actual = (wrist_lm.x, wrist_lm.y)
        if self.wrist_anterior is None:
            self.wrist_anterior = wrist_actual
            return False, 0.0
        dx = wrist_actual[0] - self.wrist_anterior[0]
        dy = wrist_actual[1] - self.wrist_anterior[1]
        mov = (dx * dx + dy * dy) ** 0.5
        self.wrist_anterior = wrist_actual
        return mov > self.umbral_movimiento, mov

    def predict(self, frame):
        self._frame_idx += 1
        results, _ = self._procesar_mediapipe(frame)

        # ---- Sin mano detectada ----
        # Perder la mano se trata como el FIN inmediato de cualquier
        # gesto en curso (no hace falta esperar los frames de "quieto",
        # ya que no hay nada que seguir midiendo).
        if not results.multi_hand_landmarks:
            if self.smoother is not None:
                self.smoother.reset()
            self.wrist_anterior = None

            resultado_dinamico = (None, 0.0, None, 0.0)
            if self.grabando_gesto:
                resultado_dinamico = self._finalizar_gesto()
                self.grabando_gesto = False
                self.frames_quieto_en_gesto = 0
            return None, 0.0, results, None, resultado_dinamico, False

        # ---- Vector de features (para el modelo estatico) ----
        if self.max_hands == 1:
            features = hand_features.build_feature_vector(
                results.multi_hand_landmarks[0], rotate=self.rotate_invariant
            )
        else:
            features = hand_features.build_two_hand_feature_vector(
                results.multi_hand_landmarks,
                getattr(results, "multi_handedness", None),
                rotate=self.rotate_invariant,
            )

        en_movimiento, _ = self._medir_movimiento(results)

        # ==================================================================
        # MODO DINAMICO PURO (para pruebas aisladas del modelo dinamico)
        # ==================================================================
        if self.modo == "dinamico":
            resultado_dinamico = self._procesar_segmentacion(features, en_movimiento)
            return None, 0.0, results, None, resultado_dinamico, en_movimiento or self.grabando_gesto

        # ==================================================================
        # MODO ESTATICO PURO (para pruebas aisladas del modelo estatico)
        # ==================================================================
        if self.modo == "estatico":
            resultado_dinamico = (None, 0.0, None, 0.0)
            if len(features) != self.meta["feature_length"]:
                # El modelo fue entrenado con otra configuracion (p.ej. 1 vs 2 manos)
                return None, 0.0, results, None, resultado_dinamico, en_movimiento
            probs = self.model.predict_proba([features])[0]
            best_idx = probs.argmax()
            label = self.encoder.inverse_transform([best_idx])[0]
            confidence = float(probs[best_idx])
            confirmed, _ = self.smoother.update(label, confidence)
            if confirmed:
                self.history.append(confirmed)
            return label, confidence, results, confirmed, resultado_dinamico, en_movimiento

        # ==================================================================
        # MODO AMBOS -> ARBITRO
        # Mientras hay un gesto dinamico en curso (moviendose, o en el
        # "periodo de gracia" antes de darlo por terminado), el estatico
        # se deja en pausa (se resetea su smoother) para no confirmar por
        # error una postura intermedia del movimiento como una seña fija.
        # ==================================================================
        resultado_dinamico = self._procesar_segmentacion(features, en_movimiento)
        gesto_activo = en_movimiento or self.grabando_gesto

        if gesto_activo:
            if self.smoother is not None:
                self.smoother.reset()
            return None, 0.0, results, None, resultado_dinamico, True

        # --- Rama ESTATICA: solo corre cuando NO hay ningun gesto dinamico en curso ---
        if len(features) != self.meta["feature_length"]:
            return None, 0.0, results, None, resultado_dinamico, False

        probs = self.model.predict_proba([features])[0]
        best_idx = probs.argmax()
        label = self.encoder.inverse_transform([best_idx])[0]
        confidence = float(probs[best_idx])

        confirmed, _ = self.smoother.update(label, confidence)
        if confirmed:
            self.history.append(confirmed)
        return label, confidence, results, confirmed, resultado_dinamico, False

    def _procesar_segmentacion(self, feature_vector, en_movimiento):
        """
        Máquina de estados de la segmentación por evento de movimiento:

          1. Si hay movimiento y no se estaba grabando ya -> empieza un
             gesto nuevo (limpia el buffer, marca grabando_gesto=True).
          2. Mientras hay movimiento -> acumula frames en el buffer y
             muestra un preview en vivo (sin confirmar todavía).
          3. Si el movimiento se detiene -> cuenta frames "quieto"
             seguidos; si se alcanza FRAMES_QUIETO_PARA_FINALIZAR, se da
             por terminado el gesto y se hace la predicción FINAL con
             toda la secuencia real capturada (ver _finalizar_gesto).
             Si aún no se alcanza ese conteo, se sigue grabando por si
             el movimiento retoma (tolera micro-pausas).
        """
        if self.modelo_dinamico is None:
            return None, 0.0, None, 0.0

        if en_movimiento:
            self.frames_quieto_en_gesto = 0
            if not self.grabando_gesto:
                self.buffer_dinamico.clear()
                self.grabando_gesto = True
            self.buffer_dinamico.append(feature_vector)
            return self._preview_en_vivo()

        if self.grabando_gesto:
            self.frames_quieto_en_gesto += 1
            if self.frames_quieto_en_gesto >= self.frames_quieto_para_finalizar:
                resultado = self._finalizar_gesto()
                self.grabando_gesto = False
                self.frames_quieto_en_gesto = 0
                return resultado
            # Periodo de gracia: todavia no se da por terminado el gesto.
            self.buffer_dinamico.append(feature_vector)
            return self._preview_en_vivo()

        return None, 0.0, None, 0.0  # sin ningun gesto en curso

    def _preview_en_vivo(self):
        """
        Muestra una predicción de referencia MIENTRAS el gesto sigue en
        curso, sin confirmar nada todavía (la confirmación real solo
        ocurre en _finalizar_gesto, cuando se tiene la secuencia
        completa). Se throttlea con CADA_N_FRAMES_PREVIEW para no llamar
        predict_proba en cada frame sin necesidad real -- el preview no
        tiene que ser perfectamente fluido, solo dar una referencia.
        """
        if len(self.buffer_dinamico) < MINIMO_FRAMES_PARA_PREDECIR:
            return None, 0.0, None, 0.0

        if self._frame_idx % CADA_N_FRAMES_PREVIEW != 0:
            return self._ultimo_dinamico

        vector_pooled = pool_sequence(list(self.buffer_dinamico))
        if len(vector_pooled) != self.meta_dinamico["feature_length"]:
            return None, 0.0, None, 0.0

        probs = self.modelo_dinamico.predict_proba([vector_pooled])[0]
        best_idx = probs.argmax()
        label_din = self.encoder_dinamico.inverse_transform([best_idx])[0]
        conf_din = float(probs[best_idx])

        resultado = (None, 0.0, label_din, conf_din)
        self._ultimo_dinamico = resultado
        return resultado

    def _finalizar_gesto(self):
        """
        Se llama UNA SOLA VEZ, justo cuando el movimiento termina (mano
        quieta el tiempo suficiente, o mano perdida). Clasifica la
        secuencia COMPLETA real del gesto (largo variable, no una
        ventana fija), y exige un margen de confianza mínimo frente a la
        segunda opción más probable antes de aceptar la confirmación --
        esto evita confirmar cuando el modelo esta practicamente
        indeciso entre dos señas parecidas.
        """
        if self.modelo_dinamico is None or len(self.buffer_dinamico) < MINIMO_FRAMES_PARA_PREDECIR:
            # Gesto demasiado corto/ruidoso como para confiar en el resultado.
            self.buffer_dinamico.clear()
            self._ultimo_dinamico = (None, 0.0, None, 0.0)
            return None, 0.0, None, 0.0

        vector_pooled = pool_sequence(list(self.buffer_dinamico))
        self.buffer_dinamico.clear()

        if len(vector_pooled) != self.meta_dinamico["feature_length"]:
            self._ultimo_dinamico = (None, 0.0, None, 0.0)
            return None, 0.0, None, 0.0

        probs = self.modelo_dinamico.predict_proba([vector_pooled])[0]
        best_idx = probs.argmax()
        label_din = self.encoder_dinamico.inverse_transform([best_idx])[0]
        conf_din = float(probs[best_idx])

        # --- Margen de confianza: top1 debe superar claramente a top2 ---
        ordenados = sorted(probs, reverse=True)
        margen = ordenados[0] - ordenados[1] if len(ordenados) > 1 else ordenados[0]

        confirma = (conf_din >= self.confidence_threshold_dinamico) and (margen >= self.margen_confianza)

        if confirma:
            self.history.append(label_din)
            resultado = (label_din, conf_din, label_din, conf_din)
        else:
            # Se reconoce algo, pero no con suficiente seguridad/margen
            # como para confirmarlo -- se muestra como referencia, no
            # como confirmación real.
            resultado = (None, 0.0, label_din, conf_din)

        self._ultimo_dinamico = resultado
        return resultado

    def draw_overlay(self, frame, label, confidence, results, confirmed,
                     resultado_dinamico=(None, 0.0, None, 0.0), en_movimiento=False):
        if results and results.multi_hand_landmarks:
            for hand_lm in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(frame, hand_lm, self.mp_hands.HAND_CONNECTIONS)

        confirmado_dinamico, _, label_dinamico_en_vivo, conf_din_vivo = resultado_dinamico

        # ---- Texto superior: estatico, o preview/estado del dinamico ----
        if en_movimiento and label_dinamico_en_vivo:
            cv2.putText(frame, f"{label_dinamico_en_vivo} ({conf_din_vivo*100:.0f}%)",
                        (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 140, 0), 2)
        elif en_movimiento:
            cv2.putText(frame, "Moviendo... (analizando)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 140, 0), 2)
        elif label:
            cv2.putText(frame, f"{label} ({confidence*100:.0f}%)", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, (100, 100, 100), 2)
        else:
            cv2.putText(frame, "Muestra tu mano", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)

        # ---- Confirmación unificada: estática o dinámica, misma posición ----
        # Si ambas confirman en el mismo frame (poco común), la estática
        # tiene prioridad visual ya que es la más instantánea de las dos.
        texto_conf = None
        color_conf = (0, 255, 0)  # verde = estática
        if confirmed:
            texto_conf = f"CONFIRMADO: {confirmed}"
            color_conf = (0, 255, 0)
        elif confirmado_dinamico:
            texto_conf = f"CONFIRMADO: {confirmado_dinamico}"
            color_conf = (255, 140, 0)  # naranja = dinámica
        if texto_conf:
            cv2.putText(frame, texto_conf, (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, color_conf, 3)

        # ---- Estado del gesto en curso: ya no es "ventana objetivo",
        # sino cuantos frames lleva grabado el evento actual ----
        if self.modelo_dinamico is not None:
            progreso = len(self.buffer_dinamico)
            h = frame.shape[0]
            estado = "grabando" if self.grabando_gesto else "en espera"
            cv2.putText(frame, f"[dinamica] {estado}: {progreso} frames", (30, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 150, 0), 2)
            
            
        # Modo activo, util para saber que se esta probando durante pruebas aisladas.
        # No funciona cuando se ejeucta normalmente el archivo
        if self.modo != "ambos":
            cv2.putText(frame, f"modo: {self.modo}", (30, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)

        return frame

    def run_webcam(self, camera_id=None):
        cap, resolved_id = camera_utils.open_camera(camera_id)
        if cap is None:
            print("[ERROR] No se encontro ninguna camara disponible")
            return

        # Baja el buffer interno de la camara: menos latencia, FPS mas estables.
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL)
        print(f"[OK] Camara {resolved_id} abierta. modo={self.modo}. "
              f"Q para salir, S para guardar captura.")

        # --- Contador de FPS suavizado, util para medir el efecto de
        # los ajustes de rendimiento (downscale, etc.) ---
        t_prev = time.time()
        fps = 0.0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[ERROR] No se pudo leer un frame de la camara")
                    break

                frame = cv2.flip(frame, 1)
                label, confidence, results, confirmed, resultado_dinamico, en_movimiento = self.predict(frame)
                frame = self.draw_overlay(frame, label, confidence, results, confirmed,
                                          resultado_dinamico, en_movimiento)

                t_now = time.time()
                dt = t_now - t_prev
                t_prev = t_now
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps > 0 else 1.0 / dt
                cv2.putText(frame, f"FPS: {fps:.1f}", (frame.shape[1] - 180, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

                cv2.imshow(NOMBRE_VENTANA, frame)

                # waitKey es quien procesa los eventos de la ventana (incluido
                # el clic en la X), por eso debe ir ANTES de revisar la propiedad.
                key = cv2.waitKey(1) & 0xFF

                # Si el usuario cerró la ventana con la X, esta propiedad
                # ya queda en < 1 justo después del waitKey de arriba.
                if cv2.getWindowProperty(NOMBRE_VENTANA, cv2.WND_PROP_VISIBLE) < 1:
                    print("[OK] Ventana cerrada por el usuario.")
                    break

                if key in (ord("q"), ord("Q")):
                    break
                elif key in (ord("s"), ord("S")):
                    fname = f"captura_{int(time.time())}.jpg"
                    cv2.imwrite(fname, frame)
                    print(f"[OK] Imagen guardada: {fname}")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            print(f"\n[OK] Historial de traduccion: {' '.join(self.history[-20:])}")

def main():
    parser = argparse.ArgumentParser(description="Traductor de señas personalizado en tiempo real")
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--hands", type=int, choices=[1, 2], default=1)
    parser.add_argument("--umbral-movimiento", type=float, default=0.015,
                         help="Sensibilidad del detector de movimiento (mas bajo = mas sensible)")
    parser.add_argument("--modo", choices=MODOS_VALIDOS, default="ambos",
                         help="ambos = normal, estatico/dinamico = pruebas aisladas")
    parser.add_argument("--input-size", type=int, default=480,
                        help="Lado mayor maximo antes de MediaPipe. 480 = rapido, 720 = preciso.")
    parser.add_argument("--frames-quieto", type=int, default=FRAMES_QUIETO_PARA_FINALIZAR,
                         help="Cuantos frames quieto seguidos = el gesto terminó (más alto = más tolerante a pausas breves)")
    parser.add_argument("--margen-confianza", type=float, default=MARGEN_CONFIANZA_MINIMO,
                         help="Diferencia mínima entre la 1ra y 2da opción para confirmar (más alto = más estricto)")
    args = parser.parse_args()

    translator = CustomSignTranslator(
        models_dir=args.models_dir,
        max_hands=args.hands,
        umbral_movimiento=args.umbral_movimiento,
        modo=args.modo,
        input_size=args.input_size,
        frames_quieto_para_finalizar=args.frames_quieto,
        margen_confianza=args.margen_confianza,
    )
    translator.run_webcam(camera_id=args.camera)


if __name__ == "__main__":
    main()