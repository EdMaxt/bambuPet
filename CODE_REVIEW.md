# CODE REVIEW — bambuPet v0.3.1

> **Fecha:** 16 de septiembre de 2026  
> **Versión revisada:** 0.3.1 (post-fixes de code review anterior)  
> **Alcance:** `main.py`, `mqtt_manager.py`, `parser.py`, `static/index.html`

---

## 📊 Resumen Ejecutivo

El proyecto recibió múltiples correcciones derivadas del review anterior (v0.3.0). Varios issues críticos fueron resueltos (XSS, firma MQTT, rotación de logs, null checks). Sin embargo, persisten problemas de arquitectura de eventos y oportunidades de mejora en robustez.

| Criticidad | Conteo | Estado |
|------------|--------|--------|
| 🔴 Bugs activos | 3 | Nuevos/Persistentes |
| 🟡 Code Smells | 6 | Algunos nuevos |
| 🟢 Mejoras | 5 | Sugerencias adicionales |

---

## ✅ Fixes Aplicados (desde v0.3.0)

Los siguientes issues fueron correctamente resueltos en esta versión:

- [x] Carga de `config.json` con try/except y defaults seguros
- [x] Firma de `_on_connect`/`_on_disconnect` corregida para paho-mqtt v2
- [x] Timer de `_on_connect` ahora se referencia y cancela en `disconnect()`
- [x] `RotatingFileHandler` implementado para `mqtt_debug.log`
- [x] XSS eliminado: `escapeHtml()` + `createElement` en vez de `innerHTML`
- [x] `raw_data` eliminado del estado enviado al frontend
- [x] Valores `null` filtrados en `PrinterStateTracker.update()`
- [x] Reset de progreso al detectar nuevo print (gcode_state → RUNNING)
- [x] Código muerto de `pywebview` eliminado
- [x] Backoff exponencial en reconexión (5s → 10s → 20s → máx 60s)
- [x] Contadores incrementales (`_connected_count`) en `MQTTManager`

---

## 🔴 Bugs Activos (v0.3.1)

### 1. Duplicación de lógica de drag/eventos
**Archivo:** `main.py`, líneas 295-394

Existe **duplicación** entre `mousePressEvent`/`mouseReleaseEvent`/`mouseMoveEvent` (líneas 295-316) y `eventFilter` (líneas 358-394). Ambos intentan manejar drag y toggle de expansión.

**Comportamiento problemático:**
- **Modo compacto**: `eventFilter` captura el evento primero (`return True`), bloqueando `mousePressEvent`. El drag funciona pero el código es confuso.
- **Modo expandido**: Solo `mousePressEvent` maneja drag; `eventFilter` no interviene.
- **Doble click**: `eventFilter` retorna `True` (línea 392-393), pero **nunca llama `_toggle_expand`**. Hacer doble click no expande la vista.

**Impacto:** Funcionalidad inconsistente, doble click inútil.

**Sugerencia:** Unificar en un solo mecanismo. Opción recomendada:
```python
# Eliminar mousePressEvent/mouseMoveEvent/mouseReleaseEvent
# Y mover toda la lógica a eventFilter, o viceversa.
```

---

### 2. Doble click capturado pero no expande
**Archivo:** `main.py`, líneas 392-393

```python
elif event_type == QEvent.Type.MouseButtonDblClick:
    return True  # Bloquea pero no expande
```

El doble click es capturado y descartado. Si el usuario espera expandir con doble click, no ocurre nada.

**Sugerencia:** Reemplazar `return True` por `self._toggle_expand(); return True`.

---

### 3. `connected_count` puede desincronizarse
**Archivo:** `mqtt_manager.py`, líneas 289-294

El contador incremental `_connected_count` se incrementa/decremente en callbacks pero:
- Si `_on_connect` se llama dos veces sin desconexión (reconnect rápido), se duplica.
- Si `loop_start()` falla silenciosamente pero `connected = True`, el contador se infla.

**Sugerencia:** Eliminar `_connected_count` y derivarlo del estado real:
```python
@property
def connected_count(self) -> int:
    return sum(1 for c in self.clients.values() if c.connected)
```
Esto garantiza consistencia a costa de una iteración ligera.

---

## 🟡 Code Smells (v0.3.1)

### 4. `import time` dentro de método
**Archivo:** `main.py`, línea 278

```python
import time
```

Aunque Python caches imports, es mala práctica. Rompe convenciones PEP 8 y confunde a linters.

**Sugerencia:** Mover al inicio del archivo.

---

### 5. `getattr` innecesario para atributo inicializado en `__init__`
**Archivo:** `main.py`, línea 279

```python
last_attempt = getattr(client, '_last_reconnect_attempt', 0)
```

`_last_reconnect_attempt` se inicializa en `LocalMQTTClient.__init__` (línea 62 de `mqtt_manager.py`). No necesita `getattr`.

**Sugerencia:** Usar acceso directo: `client._last_reconnect_attempt`.

---

### 6. `runJavaScript` sin verificar página lista
**Archivo:** `main.py`, líneas 193-194

```python
js = f"window.bambuPet && window.bambuPet.updateState({json_state});"
self.webview.page().runJavaScript(js)
```

Si se llama antes de que `_on_load_finished` inyecte la API, falla silenciosamente. No hay retry ni feedback al usuario.

**Sugerencia:** Verificar `self.webview.page().isLoaded()` o encolar llamadas hasta que `loadFinished` emita.

---

### 7. CSS sin clase para estado "unknown"
**Archivo:** `index.html` / `parser.py`

`parse_printer_status` puede retornar `"unknown"` (línea 136 de `parser.py`), pero no existe `.status-unknown` en CSS. El pet queda sin estilo visible.

**Sugerencia:** Agregar:
```css
.status-unknown { background: rgba(150, 150, 150, 0.3); color: #ccc; }
```

---

### 8. Lógica de estado en parser es densa
**Archivo:** `parser.py`, líneas 37-45

La máquina de estados para detectar nuevo print es correcta pero difícil de leer:
```python
if prev_state == "RUNNING" and print_data["gcode_state"] == "RUNNING":
    pass
elif print_data["gcode_state"] == "RUNNING" and prev_state != "RUNNING":
    if "mc_percent" not in print_data:
        self.last_known["mc_percent"] = 0
```

**Sugerencia:** Agregar comentario tipo state machine:
```
# States: IDLE → RUNNING (reset progress if no mc_percent)
#         RUNNING → RUNNING (preserve progress)
#         RUNNING → IDLE (preserve last known)
```

---

### 9. `request_full_status` sin rate limiting
**Archivo:** `mqtt_manager.py`, líneas 196-206

Si `request_all_status()` se llama repetidamente (bug, timer rápido), podría floodear la red local.

**Sugerencia:** Agregar debounce de 2 segundos:
```python
def request_full_status(self):
    if time.time() - getattr(self, '_last_pushall', 0) < 2:
        return
    self._last_pushall = time.time()
    # ... resto del código
```

---

## 🟢 Mejoras Sugeridas

### 10. Mejorar parsing de mensajes frontend
**Archivo:** `main.py`, línea 321

```python
parts = message.split(":", 2)
```

Si el valor contiene `":"` (ej: `"scale:100:extra"`), el split lo corrompe. Aunque actualmente solo se usan números, es frágil.

**Sugerencia:** Usar JSON estructurado:
```javascript
// Frontend
console.log('bambuPet:' + JSON.stringify({action: 'scale', value: 100}));
```
```python
# Python
data = json.loads(message[len("bambuPet:"):])
```

---

### 11. Validar tipo de `lights_report`
**Archivo:** `parser.py`, línea 72

```python
lights_data = raw_data.get("lights_report", [{}])[0] if raw_data.get("lights_report") else {}
```

Si `lights_report` es un dict en vez de lista, `.get("mode")` funciona pero la lógica es inconsistente.

**Sugerencia:** Validar tipo:
```python
lights_report = raw_data.get("lights_report", [])
lights_data = lights_report[0] if isinstance(lights_report, list) and lights_report else {}
```

---

### 12. Debounce en sliders
**Archivo:** `index.html`, líneas 521-535

Los sliders notifican a Python en cada evento `input`. Si se mueve rápido, se envían decenas de mensajes.

**Sugerencia:** Debounce de 150ms:
```javascript
let debounceTimer;
this.elements.sliderSize.addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
        window.bambuPetAPI.receive_message('scale', val);
    }, 150);
});
```

---

### 13. Agregar `.gitignore`
No existe `.gitignore` en el proyecto. Archivos que deberían excluirse:
```
config.json
mqtt_debug.log
__pycache__/
*.pyc
```

---

### 14. Considerar QWebChannel para comunicación robusta
El mecanismo actual (`console.log` → `javaScriptConsoleMessage`) es funcional pero frágil. **QWebChannel** permitiría:
- Llamadas directas Python↔JS sin parsing de strings
- Callbacks con confirmación
- Tipado fuerte

**Impacto:** Medio-Alto (requiere reestructurar comunicación).

---

## 📋 Plan de Acción Recomendado (v0.3.1)

### Prioridad Alta
1. [ ] **Unificar manejo de eventos** — Elegir entre eventFilter o mouse events, no ambos
2. [ ] **Arreglar doble click** — Hacer que expanda en vez de solo bloquear
3. [ ] **Eliminar `_connected_count` incremental** — Derivar de estado real

### Prioridad Media
4. [ ] Mover `import time` al inicio de `main.py`
5. [ ] Reemplazar `getattr` por acceso directo
6. [ ] Agregar `.gitignore`
7. [ ] CSS para `.status-unknown`
8. [ ] Validar tipo de `lights_report`

### Prioridad Baja
9. [ ] Rate limiting en `request_full_status`
10. [ ] Debounce en sliders frontend
11. [ ] QWebChannel (mejora futura)
12. [ ] Comentarios de state machine en parser

---

## 📝 Notas Finales

El proyecto muestra una evolución positiva desde v0.3.0. Los fixes de seguridad (XSS), logging (rotación) y robustez (null checks, backoff) demuestran响应ividad a feedback.

Los problemas restantes son principalmente de **consistencia arquitectónica** (duplicación de eventos) y **defensas profundas** (parsing frágil, race conditions). Ninguno es bloqueante para uso personal, pero deberían resolverse antes de un release público.

> 🐼 **bambuPet v0.3.1** — Buen progreso, hardening casi completo.
