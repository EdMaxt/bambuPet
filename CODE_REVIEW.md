# CODE REVIEW — bambuPet v0.3.0

> Fecha: 14 de septiembre de 2026  
> Revisor: Code Review Técnico  
> Alcance: `main.py`, `mqtt_manager.py`, `parser.py`, `static/index.html`

---

## 📊 Resumen Ejecutivo

| Criticidad | Conteo |
|------------|--------|
| 🔴 Bugs / Seguridad | 4 |
| 🟡 Code Smells | 8 |
| 🟢 Mejoras / Sugerencias | 7 |

El proyecto compila y corre correctamente, pero presenta **riesgos de seguridad XSS**, **manejo de errores inconsistente**, y un **mecanismo de comunicación frontend→Python frágil**. A continuación, el análisis detallado.

---

## 1. `main.py`

### 🔴 Bugs

#### 1.1 — Event filter con coordenadas desalineadas (línea 287-298)
```python
def eventFilter(self, obj, event):
    if self._compact_mode and obj == self.webview:
        if event.type() in (...):
            QApplication.sendEvent(self, event)
            return True
```
**Problema**: Los eventos de mouse tienen coordenadas relativas al `webview`. Al reenviarlos a `self` (la ventana), las coordenadas no se traducen. Si el layout tuviera márgenes o el webview no ocupara el 100% de la ventana, el drag calcularía offsets incorrectos.  
**Impacto**: Bajo (actualmente el webview llena toda la ventana).  
**Solución**: Mapear coordenadas con `obj.mapToGlobal()` o usar `self.handleDrag()` directamente en lugar de reenviar el evento crudo.

#### 1.2 — Carga de configuración sin manejo de errores (línea 19-20)
```python
with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)
```
**Problema**: Si `config.json` no existe, tiene JSON inválido, o lacks permisos, la app crashea sin mensaje útil. Además, se ejecuta al importar el módulo, no al instanciar.  
**Solución**: Envolver en try/except con mensaje descriptivo y defaults.

### 🟡 Code Smells

#### 1.3 — Mezcla de responsabilidades
`PandaPetWindow` hace demasiado: UI, drag, timers, parsing de mensajes JS, estado MQTT.  
**Sugerencia**: Extraer el manejo de eventos a una clase `PetWindowBehavior` o usar mixins.

#### 1.4 — `print()` vs `logging`
Se usa `print()` en toda `main.py` pero `mqtt_manager.py` usa `logging`. Inconsistente.  
**Sugerencia**: Usar `logging` en toda la app con niveles configurables.

#### 1.5 — `drag_start` condicional (línea 241)
```python
if hasattr(self, 'drag_start'):
```
Verificar existencia de atributo en cada release es diseño frágil. Mejor inicializar en `__init__`.

### 🟢 Mejoras

#### 1.6 — Persistir scale/opacity en config.json
Los sliders guardan en `localStorage` (frontend) y notifican a Python, pero al reiniciar la app, Python lee de `config.json` (defaults). Los valores del localStorage nunca se escriben en config.json.  
**Sugerencia**: Que Python persista los cambios en `config.json` cuando recibe scale/opacity.

---

## 2. `mqtt_manager.py`

### 🔴 Bugs

#### 2.1 — Firma de `_on_connect` incorrecta para paho-mqtt v2 (línea 54)
```python
def _on_connect(self, client, userdata, flags, rc, properties=None):
```
**Problema**: En paho-mqtt v2, el cuarto parámetro es `reason_code` (un objeto), no `rc` (int). Aunque el código funciona si `rc` llega como int por compatibilidad, podría romperse en versiones futuras. Lo mismo aplica para `_on_disconnect`.  
**Solución**: Usar la firma oficial: `(client, userdata, flags, reason_code, properties)`.

#### 2.2 — Timer huérfano en `_on_connect` (línea 63-64)
```python
import threading
threading.Timer(0.5, self.request_full_status).start()
```
**Problemas**:
- Re-importa `threading` (ya importado arriba).
- Si el cliente se desconecta antes de 0.5s, el timer intentará publicar en un cliente potencialmente inválido.
- El timer no se cancela ni se referencia — no se puede limpiar.

**Sugerencia**: Guardar referencia del timer y cancelarlo en `disconnect()`.

### 🟡 Code Smells

#### 2.3 — Log a archivo sin rotación (línea 87-89)
```python
with open("mqtt_debug.log", "a") as f:
    f.write(...)
```
En cada mensaje MQTT se abre, escribe y cierra un archivo. Sin rotación ni límite de tamaño. Una impresora activa puede llenar el disco.  
**Sugerencia**: Usar `RotatingFileHandler` de logging o desactivar en producción.

#### 2.4 — `logging.basicConfig` en módulo (línea 18)
```python
logging.basicConfig(level=logging.INFO, ...)
```
Se ejecuta al importar. Si otro módulo importa `mqtt_manager`, configura el logging globalmente — efecto secundario no deseado.  
**Sugerencia**: Mover a `if __name__ == "__main__"` o a función de setup explícita.

#### 2.5 — Propiedades `connected_count` / `total_count` ineficientes (línea 243-251)
Se llaman en cada `_inject_state()` (cada mensaje MQTT). Iteran sobre todos los clientes cada vez.  
**Sugerencia**: Mantener contadores incrementales actualizados en `_handle_connect`/`_handle_disconnect`.

### 🟢 Mejoras

#### 2.6 — TLS inseguro sin advertencia
```python
self.client.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS)
self.client.tls_insecure_set(True)
```
Aunque es necesario para BambuLab self-signed, debería loguearse una advertencia visible al usuario la primera vez.

#### 2.7 — Backoff exponencial para reconexión
`main.py` reconecta cada 5 segundos fijo. Si la impresora está apagada, genera tráfico innecesario.  
**Sugerencia**: Implementar backoff exponencial (5s, 10s, 20s, máx 60s).

---

## 3. `parser.py`

### 🟡 Code Smells

#### 3.1 — `raw_data` incluido en estado parseado (línea 95)
```python
"raw": raw_data,
```
**Problema**: El diccr completo del mensaje MQTT se incluye en el estado que se serializa a JSON y se envía al frontend vía `runJavaScript`. Mensajes grandes pueden:
- Saturar el canal JS.
- Causar performance issues en el parseo JSON de Qt.
- Exponer datos internos.

**Sugerencia**: Eliminar `raw` del estado enviado al frontend o incluir solo campos específicos de debug.

#### 3.2 — Valores nulos no filtrados (línea 27-28)
```python
if "mc_percent" in print_data:
    self.last_known["mc_percent"] = print_data["mc_percent"]
```
Si el mensaje trae `{"print": {"mc_percent": null}}`, se guarda `None` en `last_known`, sobrescribiendo un valor válido anterior.  
**Sugerencia**: Verificar `if print_data.get("mc_percent") is not None`.

#### 3.3 — Doble parsing implícito
`PrinterStateTracker.update()` llama a `get_enriched_state()` que llama a `parse_printer_status()`. Los datos crudos se parsean aunque el tracker ya tiene valores conocidos.  
**Sugerencia**: Solo parsear campos faltantes, no todo el mensaje.

### 🟢 Mejoras

#### 3.4 — Reset de tracker al iniciar nueva impresión
Si se inicia un nuevo print, el tracker conserva el progreso del print anterior hasta que llegue un nuevo `mc_percent`.  
**Sugergia**: Detectar cambio de `gcode_state` a `RUNNING` y resetear `mc_percent` a 0.

---

## 4. `static/index.html`

### 🔴 Seguridad

#### 4.1 — XSS vía `innerHTML` con datos del servidor (línea 700-717)
```javascript
container.innerHTML = printers.map(p => {
    const fileStr = p.current_file ? `<div ...>📄 ${p.current_file}</div>` : '';
    return `
        <div class="printer-card">
            <div class="printer-name">🖨️ ${p.name}</div>
            ...
            ${fileStr}
        </div>
    `;
}).join('');
```
**Problema**: Si `p.name` o `p.current_file` contienen HTML (ej: `<img src=x onerror=alert(1)>` o `<script>...</script>`), se ejecuta JavaScript arbitrario. Un nombre de archivo malicioso en la impresora (o un MQTT inyectado) compromete la app.  
**Impacto**: **Alto** — aunque la fuente es "local" (MQTT de impresora), un ataque MITM en la red local podría inyectar payloads.  
**Solución**: Escapar HTML antes de insertar, o usar `textContent` y createElement en lugar de template literals.

### 🟡 Code Smells

#### 4.2 — Código muerto: `window.pywebview` (línea 527, 540)
```javascript
if (window.pywebview) {
    window.pywebview.api.set_scale(parseInt(val));
} else if (window.bambuPetAPI) {
    ...
}
```
`pywebview` es un framework diferente (no PyQt5). Estas líneas nunca se ejecutan.  
**Sugerencia**: Eliminar.

#### 4.3 — Sin escape de HTML en `printerNameCompact` (línea 587)
```javascript
this.elements.printerNameCompact.textContent = activePrinter.name || 'Printer';
```
Esta línea usa `textContent` (seguro), pero `p.name` en `renderPrintersList` usa `innerHTML` (inseguro). Inconsistente.

### 🟢 Mejoras

#### 4.4 — Debounce en sliders
Los sliders notifican a Python en cada evento `input`. Si se mueve rápido, se envían decenas de mensajes.  
**Sugerencia**: Debounce de 100-200ms antes de llamar a `bambuPetAPI.receive_message`.

---

## 5. Comunicación Frontend → Python (console.log + eventFilter)

### Arquitectura actual:
```
[Slider JS] → console.log('bambuPet:scale:100')
     ↓
[QWebEnginePage.javaScriptConsoleMessage]
     ↓
[_on_js_console_message parsea string]
     ↓
[Aplica cambio en ventana]
```

### Problemas identificados:

| Problema | Criticidad | Descripción |
|----------|------------|-------------|
| **Sin confirmación** | 🟡 | El frontend no sabe si Python recibió/procesó el mensaje. |
| **Pérdida de mensajes** | 🟡 | Console.log es best-effort. Mensajes rápidos pueden coalescer. |
| **Parsing frágil** | 🟡 | Split por `:`. Si el valor contiene `:`, se corrompe. |
| **Sin serialización** | 🟡 | No hay request_id para correlacionar. |
| **Formato implícito** | 🟡 | `action:value` es un protocolo no documentado. |

### Sugerencia de mejora:
Implementar **QWebChannel** para comunicación bidireccional real:
- Permite llamadas directas Python↔JS.
- Es soportado nativamente por PyQt5.
- Elimina la necesidad de parsing de strings.

Alternativa rápida: usar `window.bambuPetAPI.receive_message()` con JSON estructurado:
```javascript
window.bambuPetAPI.receive_message(JSON.stringify({action: 'scale', value: 100}));
```
Y en Python:
```python
data = json.loads(message.split(":", 1)[1])
```

---

## 6. Otros Hallazgos

### 6.1 — `dashboard/` carpeta sin conectar
Existe una carpeta `dashboard/` con su propio `index.html`, `style.css`, `app.js` que no está conectada a `main.py`. Genera confusión sobre cuál es el frontend activo.

### 6.2 — Sin validación de configuración
`config.json` no se valida al cargar. Si falta un campo (`access_code`, `serial`), la app crashea en tiempo de ejecución con `KeyError`.  
**Sugerencia**: Usar un schema o validación explícita.

### 6.3 — Sin graceful degradation
Si MQTT falla, el pet queda congelado en el último estado. El usuario no sabe si:
- La impresora está offline.
- La red falló.
- El access_code expiró.

**Sugercia**: Mostrar indicador de "stale data" si no se reciben mensajes en X segundos.

---

## 📋 Plan de Acción Recomendado

### Prioridad Alta (Seguridad)
1. [ ] Escapar HTML en `renderPrintersList` y todo `innerHTML` con datos del servidor.
2. [ ] Eliminar código muerto (`pywebview`).

### Prioridad Media (Robustez)
3. [ ] Corregir firmas de callbacks MQTT para paho-mqtt v2.
4. [ ] Agregar try/except en carga de `config.json`.
5. [ ] Validar valores nulos en `PrinterStateTracker.update()`.
6. [ ] Eliminar `raw_data` del estado enviado al frontend.
7. [ ] Agregar rotación de logs o desactivar `mqtt_debug.log` por defecto.

### Prioridad Baja (Mejoras)
8. [ ] Implementar QWebChannel para comunicación frontend↔Python.
9. [ ] Unificar logging (usar `logging` en toda la app).
10. [ ] Persistir scale/opacity en `config.json` desde Python.
11. [ ] Implementar backoff exponencial en reconexiones.
12. [ ] Debounce en sliders frontend.
13. [ ] Agregar stale-data indicator si no hay mensajes MQTT en X tiempo.

---

## 📝 Notas Finales

El proyecto es funcional y demuestra dominio de PyQt5 + MQTT. Los problemas encontrados son típicos de un prototipo en evolución. La corrección del XSS y la estabilización de la comunicación frontend↔Python deberían ser las próximas prioridades antes de considerar un release público.

> 🐼 **bambuPet** — buen proyecto, necesita hardening de seguridad.

---

## 🔬 Análisis Adicional con qwen2.5-coder:14B (Ollama Local)

Se corrió un segundo análisis automatizado con `qwen2.5-coder:14b` local que validó y complementó los hallazgos previos:

### Confirmados por modelo local:
1. **Race condition en `_on_mqtt_message`**: Actualización de `self.printer_states` e inyección a UI no es atómica si llegan mensajes simultáneos de múltiples impresoras.
2. **Falta de sanitización XSS**: Confirmado en `p.current_file` — el modelo sugiere función `escapeHtml()` explícita.
3. **QWebEngineView memory**: El modelo advierte sobre uso intensivo de memoria si el HTML/CSS/JS crece en complejidad.
4. **Reconexión sin backoff**: Reintentar cada 5s fijo puede generar tormenta de reconexión si múltiples impresoras están offline simultáneamente.

### Hallazgo adicional:
5. **Sin verificación de certificado TLS**: Aunque necesario para self-signed de BambuLab, debería haber un one-time warning al usuario aceptando el riesgo.

---

## 📊 Resumen Final de Hallazgos

| # | Archivo | Línea | Tipo | Criticidad | Descripción |
|---|---------|-------|------|------------|-------------|
| 1 | `index.html` | 700-717 | XSS | 🔴 Alta | `innerHTML` con `p.name` y `p.current_file` sin escapar |
| 2 | `main.py` | 19-20 | Crasheo | 🔴 Alta | `config.json` sin try/except ni validación de schema |
| 3 | `mqtt_manager.py` | 54 | Bug | 🟡 Media | Callback `_on_connect` con firma paho v2 incorrecta (rc vs reason_code) |
| 4 | `mqtt_manager.py` | 63-64 | Mem leak | 🟡 Media | Timer huérfano sin referencia ni cleanup en disconnect |
| 5 | `mqtt_manager.py` | 87-89 | Perf | 🟡 Media | Log a archivo sin rotación (mqtt_debug.log) |
| 6 | `parser.py` | 27-28 | Bug | 🟡 Media | Valores `null` sobrescriben `last_known` válidos |
| 7 | `parser.py` | 95 | Perf | 🟡 Media | `raw_data` completo enviado a frontend innecesariamente |
| 8 | `main.py` | 287-298 | Bug | 🟡 Media | Event filter reenvía eventos sin mapear coordenadas |
| 9 | `mqtt_manager.py` | 164 | Race | 🟡 Media | `_on_mqtt_message` no es atómica (state + UI) |
| 10 | `index.html` | 527,540 | Muerto | 🟡 Baja | Referencias a `pywebview` (framework diferente) |
| 11 | `mqtt_manager.py` | 243-251 | Perf | 🟡 Baja | Contadores recomputados en cada mensaje |
| 12 | `main.py` | 241 | Smell | 🟡 Baja | `hasattr` en lugar de inicializar en `__init__` |
| 13 | `main.py` | 172-201 | Perf | 🟡 Baja | Sin backoff exponencial en reconexión MQTT |

---

## ✅ Checklist de Fixes Aplicados

```
[ ] 1. Agregar escapeHtml() y sanitizar todo innerHTML con datos MQTT
[ ] 2. Envolver carga de config.json en try/except con defaults
[ ] 3. Corregir firmas de callbacks MQTT (reason_code en lugar de rc)
[ ] 4. Guardar referencia del timer en _on_connect y cancelar en disconnect()
[ ] 5. Usar RotatingFileHandler o desactivar mqtt_debug.log
[ ] 6. Filtrar valores null en PrinterStateTracker.update()
[ ] 7. Eliminar "raw" del estado enviado a frontend
[ ] 8. Mapear coordenadas en eventFilter
[ ] 9. Eliminar código muerto de pywebview
[ ] 10. Mantener contadores incrementales en MQTTManager
[ ] 11. Implementar backoff exponencial en reconexión
[ ] 12. Agregar stale-data indicator si no hay mensajes MQTT
[ ] 13. Validar config.json al inicio (todos los campos requeridos)
```
