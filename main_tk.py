"""
bambuPet — Desktop widget con Tkinter para monitoreo de impresoras BambuLab
v0.1.0 — Versión Tkinter (sin dependencias pesadas)
"""

import sys
import json
import os
import math
import random
import logging
from tkinter import Tk, Canvas, Label, Frame, BOTH, TOP, LEFT, RIGHT, X, Y, NW, SW, NE, E, W, DISABLED, NORMAL

# Configuración de logging
logger = logging.getLogger(__name__)

# Cargar configuración con defaults seguros
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    """Cargar configuración con manejo de errores."""
    defaults = {
        "mqtt": {"poll_interval_sec": 10, "reconnect_delay_sec": 5, "printers": []},
        "display": {"position": "bottom-right", "offset_x": 20, "offset_y": 20, "scale": 1.0, "opacity": 0.95, "always_on_top": True},
        "pet": {"celebration_duration_sec": 5, "show_printer_name": True, "compact_mode": "most_progress"}
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        for key, value in defaults.items():
            if key not in user_config:
                user_config[key] = value
            elif isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if subkey not in user_config[key]:
                        user_config[key][subkey] = subvalue
        return user_config
    except FileNotFoundError:
        logger.warning(f"config.json no encontrado en {CONFIG_PATH}, usando defaults")
        return defaults
    except json.JSONDecodeError as e:
        logger.error(f"config.json invalido: {e}, usando defaults")
        return defaults
    except Exception as e:
        logger.error(f"Error cargando config: {e}, usando defaults")
        return defaults


# ============================================================
# BAMBU PET WIDGET — Clase principal
# ============================================================

class BambuPetWidget:
    """
    Widget desktop transparente con Tkinter.
    Muestra progreso de impresoras BambuLab en un circulo animado.
    """

    # Tamanos de ventana
    COMPACT_W = 150
    COMPACT_H = 150
    EXPANDED_W = 350
    EXPANDED_H = 300

    # Colores del pet
    BG_COLOR = "#010101"          # Color transparente (evitar #000000)
    CYAN = "#00e5ff"
    GREEN = "#6bcb77"
    YELLOW = "#ffd93d"
    RED = "#ff6b6b"
    DARK_BG = "#1a1a2e"
    LIGHT_BG = "#16213e"
    TEXT_COLOR = "#e0e0e0"

    def __init__(self):
        """Inicializar el widget."""
        # Crear ventana principal
        self.root = Tk()
        self.root.overrideredirect(True)                      # Sin bordes
        self.root.attributes('-topmost', True)                 # Siempre visible
        self.root.attributes('-transparentcolor', self.BG_COLOR)  # Transparencia

        # Variables de estado
        self.expanded = False
        self.progress = 0
        self.status = "idle"          # idle, printing, paused, done, error
        self.printer_name = "Esperando..."
        self.nozzle_temp = 0
        self.bed_temp = 0
        self.current_file = ""

        # Variables de drag
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_moved = False
        self.drag_threshold = 5       # pixeles para considerar drag vs click

        # Variables de animacion
        self.animation_phase = 0
        self.pulse_scale = 1.0
        self.glow_intensity = 0
        self.confetti_particles = []

        # Cargar configuracion
        self.config = load_config()

        # Configurar UI
        self._setup_ui()

        # Posicionar ventana
        self._position_window()

        # Vincular eventos de drag
        self._bind_drag_events()

        # Iniciar loop de animacion
        self._schedule_animations()

        logger.info("bambuPet Tkinter iniciado")

    # --------------------------------------------------------
    # Setup UI
    # --------------------------------------------------------

    def _setup_ui(self):
        """Crear canvas y elementos visuales del pet."""
        self.canvas = Canvas(
            self.root,
            width=self.COMPACT_W,
            height=self.COMPACT_H,
            bg=self.BG_COLOR,
            highlightthickness=0,
            cursor="hand2"
        )
        self.canvas.pack(fill=BOTH, expand=True)

        # Dibujar elementos iniciales
        self._draw_compact()

    def _draw_compact(self):
        """Dibujar vista compacta del pet (circulo + B + anillo)."""
        self.canvas.delete("all")

        cx = self.COMPACT_W // 2
        cy = self.COMPACT_H // 2
        r = 60  # Radio del circulo principal

        # Calcular radio con pulso de animacion
        pulse_r = int(r * self.pulse_scale)

        # 1. Circulo de fondo (gradiente verde-azul simulado con 2 circulos)
        self.canvas.create_oval(
            cx - pulse_r, cy - pulse_r,
            cx + pulse_r, cy + pulse_r,
            fill=self.LIGHT_BG, outline=""
        )
        inner_r = pulse_r - 4
        self.canvas.create_oval(
            cx - inner_r, cy - inner_r,
            cx + inner_r, cy + inner_r,
            fill=self.DARK_BG, outline=self.CYAN, width=2
        )

        # 2. Anillo de progreso (arco)
        self._draw_progress_ring(cx, cy, pulse_r + 8)

        # 3. Letra "B" en el centro
        font_size = int(28 * self.pulse_scale)
        self.canvas.create_text(
            cx, cy,
            text="B",
            font=("Consolas", font_size, "bold"),
            fill=self.CYAN
        )

        # 4. Texto de progreso debajo (si hay progreso)
        if self.progress > 0:
            self.canvas.create_text(
                cx, cy + pulse_r + 18,
                text=f"{self.progress}%",
                font=("Arial", 10, "bold"),
                fill=self.GREEN
            )

        # 5. Indicador de estado (punto pequeno)
        status_color = self._get_status_color()
        self.canvas.create_oval(
            cx + pulse_r - 8, cy - pulse_r + 4,
            cx + pulse_r + 2, cy - pulse_r + 14,
            fill=status_color, outline=""
        )

        # 6. Nombre de impresora (si hay)
        if self.config.get("pet", {}).get("show_printer_name", True):
            self.canvas.create_text(
                cx, 12,
                text=self.printer_name[:12],
                font=("Arial", 8),
                fill=self.TEXT_COLOR
            )

    def _draw_progress_ring(self, cx, cy, r):
        """Dibujar anillo de progreso alrededor del circulo."""
        # Anillo de fondo (gris oscuro)
        self.canvas.create_oval(
            cx - r, cy - r,
            cx + r, cy + r,
            outline="#333333", width=4
        )

        if self.progress <= 0:
            return

        # Calcular angulo de progreso (0-360 grados)
        extent = (self.progress / 100.0) * 360

        # Crear arco de progreso usando create_arc
        # Tkinter arcs: start=0 es las 3 en punto, crecen en sentido antihorario
        # Queremos que empiece arriba (12 en punto) y crezca en sentido horario
        start_angle = 90  # Arriba
        color = self._get_progress_color()

        # Dibujar arco con linea ancha
        x1 = cx - r
        y1 = cy - r
        x2 = cx + r
        y2 = cy + r

        # Usar create_arc para el progreso
        self.canvas.create_arc(
            x1, y1, x2, y2,
            start=start_angle,
            extent=-extent,  # Negativo para sentido horario
            style="arc",
            outline=color,
            width=4
        )

    def _draw_expanded(self):
        """Dibujar vista expandida con panel de informacion."""
        self.canvas.delete("all")

        w = self.EXPANDED_W
        h = self.EXPANDED_H

        # Fondo del panel expandido (con esquinas redondeadas simuladas)
        self._draw_rounded_rect(5, 5, w - 5, h - 5, 15, self.DARK_BG, self.CYAN)

        # Header
        self.canvas.create_text(
            w // 2, 20,
            text=f"🖨 {self.printer_name}",
            font=("Arial", 12, "bold"),
            fill=self.CYAN,
            anchor=N
        )

        # Separador
        self.canvas.create_line(15, 35, w - 15, 35, fill="#333333", width=1)

        # Progreso grande
        self.canvas.create_text(
            w // 2, 70,
            text=f"{self.progress}%",
            font=("Arial", 28, "bold"),
            fill=self._get_progress_color()
        )

        # Anillo de progreso pequeno a la derecha
        ring_cx = w - 50
        ring_cy = 70
        ring_r = 30
        self._draw_progress_ring(ring_cx, ring_cy, ring_r)

        # Estado
        status_text = self._get_status_text()
        status_color = self._get_status_color()
        self.canvas.create_text(
            20, 110,
            text=f"Estado: {status_text}",
            font=("Arial", 10),
            fill=status_color,
            anchor=W
        )

        # Archivo actual
        file_display = self.current_file[:30] + "..." if len(self.current_file) > 30 else self.current_file
        self.canvas.create_text(
            20, 135,
            text=f"Archivo: {file_display or '-'}",
            font=("Arial", 9),
            fill=self.TEXT_COLOR,
            anchor=W
        )

        # Temperaturas
        self.canvas.create_text(
            20, 165,
            text=f"Boquilla: {self.nozzle_temp}°C",
            font=("Arial", 10),
            fill=self.YELLOW if self.nozzle_temp > 0 else self.TEXT_COLOR,
            anchor=W
        )

        self.canvas.create_text(
            20, 190,
            text=f"Cama: {self.bed_temp}°C",
            font=("Arial", 10),
            fill=self.YELLOW if self.bed_temp > 0 else self.TEXT_COLOR,
            anchor=W
        )

        # Barra de progreso lineal
        bar_x = 20
        bar_y = 220
        bar_w = w - 40
        bar_h = 12
        self.canvas.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
                                      outline="#333333", fill="#111111")
        fill_w = int(bar_w * (self.progress / 100.0))
        if fill_w > 0:
            self.canvas.create_rectangle(bar_x, bar_y, bar_x + fill_w, bar_y + bar_h,
                                          fill=self._get_progress_color(), outline="")

        # Footer con instruccion
        self.canvas.create_text(
            w // 2, h - 15,
            text="Click para minimizar",
            font=("Arial", 8),
            fill="#666666",
            anchor=S
        )

    def _draw_rounded_rect(self, x1, y1, x2, y2, radius, fill, outline):
        """Dibujar rectangulo con esquinas redondeadas."""
        # Usar poligono para simular esquinas redondeadas
        points = []
        # Arriba-izquierda
        for i in range(90, 180):
            rad = math.radians(i)
            px = x1 + radius + int(radius * math.cos(rad))
            py = y1 + radius + int(radius * math.sin(rad))
            points.extend([px, py])
        # Arriba-derecha
        for i in range(0, 90):
            rad = math.radians(i)
            px = x2 - radius + int(radius * math.cos(rad))
            py = y1 + radius + int(radius * math.sin(rad))
            points.extend([px, py])
        # Abajo-derecha
        for i in range(270, 360):
            rad = math.radians(i)
            px = x2 - radius + int(radius * math.cos(rad))
            py = y2 - radius + int(radius * math.sin(rad))
            points.extend([px, py])
        # Abajo-izquierda
        for i in range(180, 270):
            rad = math.radians(i)
            px = x1 + radius + int(radius * math.cos(rad))
            py = y2 - radius + int(radius * math.sin(rad))
            points.extend([px, py])

        self.canvas.create_polygon(points, fill=fill, outline=outline, width=1, smooth=False)

    def _get_status_color(self):
        """Obtener color segun estado actual."""
        colors = {
            "idle": self.TEXT_COLOR,
            "printing": self.CYAN,
            "paused": self.YELLOW,
            "done": self.GREEN,
            "error": self.RED,
            "preparing": self.YELLOW,
            "finished": self.GREEN,
            "unknown": "#888888"
        }
        return colors.get(self.status, self.TEXT_COLOR)

    def _get_progress_color(self):
        """Obtener color del progreso segun porcentaje."""
        if self.progress < 30:
            return self.CYAN
        elif self.progress < 70:
            return self.GREEN
        else:
            return self.YELLOW

    def _get_status_text(self):
        """Obtener texto legible del estado."""
        texts = {
            "idle": "Inactiva",
            "printing": "Imprimiendo",
            "paused": "Pausada",
            "done": "Completado",
            "error": "Error",
            "preparing": "Preparando",
            "finished": "Finalizado",
            "unknown": "Desconocido"
        }
        return texts.get(self.status, self.status)

    # --------------------------------------------------------
    # Sistema de Drag
    # --------------------------------------------------------

    def _bind_drag_events(self):
        """Vincular eventos de mouse para drag."""
        # Usar el canvas y la ventana raiz
        for widget in [self.canvas, self.root]:
            widget.bind('<Button-1>', self._on_mouse_down)
            widget.bind('<B1-Motion>', self._on_mouse_move)
            widget.bind('<ButtonRelease-1>', self._on_mouse_up)

    def _on_mouse_down(self, event):
        """Iniciar posible drag."""
        self.dragging = True
        self.drag_moved = False
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root

    def _on_mouse_move(self, event):
        """Mover ventana durante drag."""
        if not self.dragging:
            return

        # Calcular desplazamiento
        dx = abs(event.x_root - self.drag_start_x)
        dy = abs(event.y_root - self.drag_start_y)

        # Marcar como movido si supera el umbral
        if dx > self.drag_threshold or dy > self.drag_threshold:
            self.drag_moved = True

            # Calcular nueva posicion
            new_x = event.x_root - self.drag_start_x + self.root.winfo_x()
            new_y = event.y_root - self.drag_start_y + self.root.winfo_y()
            self.root.geometry(f"+{new_x}+{new_y}")

    def _on_mouse_up(self, event):
        """Terminar drag o detectar click simple."""
        if self.dragging:
            self.dragging = False

            # Si no se movio significativamente, es click simple
            if not self.drag_moved:
                self._toggle_expand()

    # --------------------------------------------------------
    # Sistema de Expansion
    # --------------------------------------------------------

    def _toggle_expand(self):
        """Alternar entre vista compacta y expandida."""
        self.expanded = not self.expanded

        if self.expanded:
            # Expandir
            self.root.geometry(f"{self.EXPANDED_W}x{self.EXPANDED_H}")
            self.canvas.config(width=self.EXPANDED_W, height=self.EXPANDED_H)
            self._draw_expanded()
            logger.info("Pet expandido")
        else:
            # Colapsar
            self.root.geometry(f"{self.COMPACT_W}x{self.COMPACT_H}")
            self.canvas.config(width=self.COMPACT_W, height=self.COMPACT_H)
            self._draw_compact()
            logger.info("Pet colapsado")

    # --------------------------------------------------------
    # Animaciones
    # --------------------------------------------------------

    def _schedule_animations(self):
        """Programar siguiente frame de animacion."""
        self._animate()
        # ~30 FPS
        self.root.after(33, self._schedule_animations)

    def _animate(self):
        """Ejecutar un frame de animacion segun estado."""
        self.animation_phase += 1

        if self.status == "idle":
            self._animate_idle()
        elif self.status == "printing":
            self._animate_printing()
        elif self.status == "done":
            self._animate_done()
        elif self.status == "error":
            self._animate_error()
        else:
            # Estado generico: idle animation
            self._animate_idle()

        # Redibujar
        if self.expanded:
            self._draw_expanded()
        else:
            self._draw_compact()

    def _animate_idle(self):
        """Animacion idle: pulso suave (1.0 - 1.05) cada ~3s."""
        # Periodo de ~3s a 30fps = ~90 frames
        period = 90
        t = self.animation_phase % period
        # Oscilacion sinusoidal suave
        self.pulse_scale = 1.0 + 0.05 * abs(math.sin(2 * math.pi * t / period))

    def _animate_printing(self):
        """Animacion de impresion: glow pulsante cyan cada ~2s."""
        period = 60  # ~2s a 30fps
        t = self.animation_phase % period
        # Glow que crece y decrece
        self.glow_intensity = int(128 + 127 * math.sin(2 * math.pi * t / period))
        # Pulso mas rapido
        self.pulse_scale = 1.0 + 0.03 * abs(math.sin(2 * math.pi * t / period))

    def _animate_done(self):
        """Animacion de completado: bounce + confetti."""
        # Bounce inicial (primeros 30 frames)
        if self.animation_phase < 30:
            t = self.animation_phase / 30.0
            # Bounce elastico
            self.pulse_scale = 1.0 + 0.2 * math.sin(t * math.pi) * (1 - t)
        else:
            self.pulse_scale = 1.0

        # Confetti
        if self.animation_phase % 5 == 0 and len(self.confetti_particles) < 50:
            cx = self.COMPACT_W // 2
            cy = self.COMPACT_H // 2
            for _ in range(3):
                self.confetti_particles.append({
                    'x': cx + random.randint(-40, 40),
                    'y': cy,
                    'vx': random.uniform(-2, 2),
                    'vy': random.uniform(-5, -2),
                    'color': random.choice([self.CYAN, self.GREEN, self.YELLOW, self.RED]),
                    'life': 60
                })

        # Actualizar y limpiar particulas
        for p in self.confetti_particles:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['vy'] += 0.15  # Gravedad
            p['life'] -= 1

        self.confetti_particles = [p for p in self.confetti_particles if p['life'] > 0]

        # Dibujar confetti en el canvas (solo si compacto)
        if not self.expanded:
            for p in self.confetti_particles:
                size = 3
                self.canvas.create_rectangle(
                    p['x'] - size, p['y'] - size,
                    p['x'] + size, p['y'] + size,
                    fill=p['color'], outline=""
                )

    def _animate_error(self):
        """Animacion de error: shake horizontal."""
        period = 20  # Shake rapido
        t = self.animation_phase % period
        if t < 10:
            shake = 3 * math.sin(2 * math.pi * t / period)
            offset_x = int(shake)
            # Aplicar offset a toda la ventana
            current_x = self.root.winfo_x()
            current_y = self.root.winfo_y()
            self.root.geometry(f"+{current_x + offset_x}+{current_y}")
        self.pulse_scale = 1.0

    # --------------------------------------------------------
    # Actualizacion de Estado
    # --------------------------------------------------------

    def update_printer_data(self, printer_name, progress, status, nozzle_temp=0, bed_temp=0, current_file=""):
        """Actualizar datos de la impresora desde MQTT."""
        self.printer_name = printer_name
        self.progress = min(100, max(0, progress))
        self.status = status
        self.nozzle_temp = nozzle_temp
        self.bed_temp = bed_temp
        self.current_file = current_file

    # --------------------------------------------------------
    # Posicionamiento
    # --------------------------------------------------------

    def _position_window(self):
        """Posicionar ventana en esquina inferior derecha."""
        self.root.update_idletasks()

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        display_config = self.config.get("display", {})
        offset_x = display_config.get("offset_x", 20)
        offset_y = display_config.get("offset_y", 20)

        x = screen_w - self.COMPACT_W - offset_x
        y = screen_h - self.COMPACT_H - offset_y - 40  # -40 para taskbar

        self.root.geometry(f"+{x}+{y}")

    # --------------------------------------------------------
    # Main Loop
    # --------------------------------------------------------

    def run(self):
        """Iniciar el loop principal de Tkinter."""
        self.root.mainloop()


# ============================================================
# Entry Point
# ============================================================

def main():
    """Entry point para bambuPet Tkinter."""
    # Configurar logging
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
        )

    logger.info("🐼 bambuPet Tkinter iniciado — Click en el pet para expandir")
    logger.info("   Arrastra para mover | ESC para cerrar (en desarrollo)")

    pet = BambuPetWidget()

    # Ejemplo de actualizacion de datos (para pruebas)
    # En produccion, esto vendria del mqtt_manager
    pet.update_printer_data(
        printer_name="Rocky",
        progress=67,
        status="printing",
        nozzle_temp=215,
        bed_temp=60,
        current_file="benchy_v3.gcode"
    )

    pet.run()


if __name__ == "__main__":
    main()
