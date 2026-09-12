# 📝 Estado del Proyecto: HandTalk (Streaming de Cámara)

Este documento resume los logros técnicos alcanzados hasta la fecha y las consideraciones críticas de infraestructura para la captura de video en tiempo real.

---

## 🚀 Guía de Lanzamiento y Acceso

Para ejecutar el servidor y acceder desde un dispositivo móvil, sigue estos pasos:

### 1. Iniciar el Servidor
Ejecuta el siguiente comando en tu terminal desde la carpeta raíz del proyecto:

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

**¿Qué significan estos parámetros?**
- `--reload`: Reinicia el servidor automáticamente cada vez que guardes un cambio en el código.
- `--host 0.0.0.0`: Indica que el servidor debe escuchar en **todas las interfaces de red**. Esto es lo que permite que tu celular (que está en otra IP) pueda conectar con tu PC.
- `--port 8000`: El puerto estándar donde correrá la aplicación.

### 2. Acceso desde el Celular (QR)
Para no escribir la IP manualmente en el móvil, lo más rápido es generar un código QR:

1. **Obtén tu IP Local:** 
   - En Windows: abre la terminal y escribe `ipconfig`. Busca la "Dirección IPv4" (ej. `192.168.1.15`).
   - En Linux/Mac: escribe `ifconfig` o `ip addr`.
2. **Crea la URL de acceso:** 
   - Combina tu IP con el puerto: `http://192.168.x.x:8000`
3. **Genera el QR:**
   - Copia esa URL y pégala en cualquier generador de QR gratuito (como [qr-code-generator.com](https://www.qr-code-generator.com/) o similares).
   - Escanea el código con la cámara de tu celular.

---

## 🚨 ALERTA CRÍTICA: Restricciones de Cámara (HTTP vs HTTPS)

Es fundamental entender que la funcionalidad principal de la aplicación (el uso de la cámara del dispositivo) depende enteramente del protocolo de conexión debido a las políticas de **Secure Contexts** de los navegadores modernos (Chrome, Safari, Firefox).

### 🛑 El Problema
El acceso a la cámara mediante `getUserMedia` **está estrictamente prohibido** en páginas cargadas vía `http://` para cualquier dirección que no sea `localhost`.

**¿Qué significa esto en la práctica?**
*   **En tu PC (`http://localhost:8000`):** La cámara **SÍ** funciona.
*   **En tu Celular (`http://192.168.x.x:8000`):** La cámara **NO** funcionará. El navegador bloqueará la solicitud por razones de seguridad, impidiendo que el celular envíe frames al servidor.

### ✅ La Solución: HTTPS es Obligatorio
Para que un dispositivo móvil pueda activar su cámara y enviar el stream al servidor, la conexión **DEBE** ser segura (`https://`).

| Escenario | Protocolo | ¿Cámara Local? | Acción Requerida |
| :--- | :--- | :--- | :--- |
| Pruebas locales | `http://localhost` | ✅ Sí | Ninguna. |
| Pruebas móvil $\rightarrow$ PC | `http://IP_Local` | ❌ **No** | **Implementar HTTPS** (ej. Ngrok). |
| Despliegue Final | `https://dominio.com` | ✅ Sí | Certificado SSL activo. |

### 🛠️ Cómo solucionar esto para pruebas rápidas
Para evitar configurar certificados SSL complejos en desarrollo, se recomienda usar **túneles HTTPS**:
1. **Ngrok / Cloudflare Tunnel:** Estas herramientas crean una URL pública segura (`https://random-id.ngrok-free.app`) que redirige el tráfico a tu puerto 8000 local. 
2. Al entrar desde el celular a esa URL HTTPS, el navegador permitirá el acceso a la cámara.

---

## ✅ Logros Alcanzados

### 1. Arquitectura de "Flujo Invertido"
Se ha implementado un sistema donde el cliente (celular/navegador) es el emisor activo y el servidor es el procesador.
- **Captura Local:** El navegador accede a la cámara del dispositivo mediante la API `getUserMedia`.
- **Extracción de Frames:** Se implementó un bucle de captura usando un `canvas` oculto que extrae frames del video cada 200ms (5 FPS), optimizando el ancho de banda.
- **Transporte Eficiente:** Los frames se convierten a JPEG (calidad 0.6) y se envían como cadenas Base64 dentro de objetos JSON a través de WebSockets.

### 2. Backend de Procesamiento (FastAPI)
- **Endpoint de Traducción:** Implementación de `/ws/translations` para recibir frames y devolver resultados de traducción.
- **Pipeline de Decodificación:** El servidor decodifica la cadena Base64 y la convierte en un array de NumPy/OpenCV, dejándolo listo para ser procesado por un modelo de IA.
- **Gestión de Conexiones:** Soporte para múltiples clientes simultáneos y manejo de desconexiones limpias.

### 3. Sistema de Respaldo (Fallback)
Para mitigar el problema de HTTPS mencionado arriba, se implementó una solución de emergencia:
- **Modo Visor:** Si el cliente detecta que no puede acceder a su propia cámara (típico en HTTP), el servidor activa la webcam de la PC y envía el stream via MJPEG (`/visor`).
- **Sincronización:** El sistema mantiene la conexión WebSocket para enviar las traducciones aunque se esté usando la cámara del servidor.
