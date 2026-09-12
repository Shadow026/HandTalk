# Propuesta de Reestructuración: Uso de HTTP vs. HTTPS en el Visor Web

> **Estado:** Pendiente de opinión de Jason antes de reestructurar formalmente las secciones 3 y 4 del plan técnico.
> **Motivo:** Durante la implementación se descubrió una limitación técnica que no estaba contemplada en el diseño original y que afecta directamente la arquitectura de red y seguridad que Jason propuso.

---

## 1. Hallazgo técnico que origina esta propuesta

El plan original (`PLAN_JIMMY.md`, sección 4.3) asume que el visor web puede operar completamente en **HTTP simple sobre la LAN**, sin necesidad de certificados. Esto es correcto para mostrar texto y video vía stream del servidor.

Sin embargo, al implementar el requisito de que **el celular use su propia cámara** para capturar las señas (en vez de depender únicamente de la webcam de la PC), se confirmó que:

> Los navegadores móviles (Chrome en Android, Safari en iOS) **bloquean el acceso a la cámara (`getUserMedia`) en cualquier origen HTTP que no sea `localhost`**. No hay forma de habilitarlo para un dispositivo cualquiera que escanee el QR sin pedirle una configuración manual (flags de navegador, cable USB), lo cual no es viable para una demo con jueces o usuarios externos.

Esto no invalida el trabajo de Jason sobre la topología de red (LAN compartida, detección de IP, no tocar el gateway) — **esa parte sigue siendo correcta y necesaria sin cambios**. Lo que sí queda en duda es si el proyecto requiere HTTPS o si conviene reestructurar el alcance para quedarse en HTTP.

---

## 2. Las dos opciones sobre la mesa

### Opción A — Quedarse en HTTP (arquitectura original de Jason, sin certificados)

**Cómo funcionaría:** El celular nunca intenta usar su propia cámara. El visor web siempre muestra la webcam de la PC vía stream (MJPEG), y la persona que hace las señas se coloca frente a la PC, no frente al celular. El celular es puramente un visor remoto de video + texto.

**Ventajas:**
- Cero complejidad adicional de certificados, sin advertencias de seguridad para el usuario final.
- Coincide 100% con la arquitectura de red ya diseñada por Jason — no hay que tocar nada de la sección 3.
- Menos piezas que pueden fallar el día de la demo (sin dependencia de `mkcert`, sin instalar nada extra).

**Desventajas:**
- Se pierde la posibilidad de que cada persona use la cámara de su propio celular para probar el traductor de forma independiente.
- El "visor" queda limitado a ser espectador, no participante activo.

### Opción B — Migrar a HTTPS local con `mkcert`

**Cómo funcionaría:** El servidor corre con un certificado autofirmado generado por el propio equipo. Cada celular que escanea el QR puede usar su propia cámara para hacer las señas, con el respaldo de caer a la cámara de la PC si algo falla.

**Ventajas:**
- Cada usuario puede probar el traductor con su propio celular, sin depender de estar físicamente frente a la PC.
- Más flexible para futuras funcionalidades (múltiples usuarios simultáneos, cada uno con su propia sesión de traducción).

**Desventajas:**
- Requiere instalar `mkcert` en la máquina que sirve el proyecto y regenerar el certificado si cambia de red/IP (por ejemplo, si el evento es en otro lugar con otro router).
- Cada dispositivo que escanea el QR ve una advertencia de "conexión no segura" la primera vez (un toque extra, pero rompe la fluidez de "escanear y ya").
- Agrega un paso más de configuración antes de la demo que puede fallar si no se prueba con anticipación.

---

## 3. Lo que cambiaría en el documento según la opción elegida

| Sección del plan | Si se elige Opción A (HTTP) | Si se elige Opción B (HTTPS) |
|---|---|---|
| 3. Arquitectura de Red | Sin cambios — se mantiene tal como Jason la diseñó | Sin cambios en la topología, solo se agrega la generación del certificado como paso adicional en el arranque |
| 4. Seguridad del Servidor | Se simplifica aún más: sin necesidad de manejar el flujo de "cámara del celular" como caso principal | Se mantiene la reestructuración ya propuesta (token simple, sin sesiones/PIN) |
| Frontend (`index.html`) | Se elimina toda la lógica de `getUserMedia` y el manejo de fallback; el visor siempre usa `/stream` | Se mantiene la lógica actual (cámara del celular con fallback a `/stream`) |
| Dependencias | Sin `mkcert`, sin necesidad de instrucciones de instalación de certificados | Se agrega `mkcert` como herramienta externa requerida (ver sección 5.5 del documento anterior) |

---

## 4. Pregunta abierta para Jason

Como la arquitectura de red y el enfoque de "no perder Internet en el host" fueron diseño tuyo, antes de reestructurar formalmente el plan de integracion necesitamos tu opinión sobre:

Que opinas al respecto, el uso de la camara si o si requierido tener una conexion https para este caso.
