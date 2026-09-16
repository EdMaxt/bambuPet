"""
bambuPet — Entry point principal con Tkinter
Integra parser.py y mqtt_manager.py en una ventana transparente interactiva.
"""

import sys
import os
import json
import logging
import tkinter as tk
from tkinter import messagebox, simpledialog, Toplevel
from typing import Dict, Any, Optional
from datetime import datetime

# Asegurar que el directorio del proyecto esté en path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from parser import PrinterStateTracker, parse_printer_status, get_print_summary
from mqtt_manager import MQTTManager

# Configuración de logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuración
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")

DEFAULT_CONFIG = {
    "mqtt": {
        "poll_interval_sec": 10,
        "reconnect_delay_sec": 5,
        "printers": []
    },
    "display": {
        "position": "bottom-right",
        "offset_x": 20,
        "offset_y": 20,
        "scale": 1.0,
        "opacity": 0.95,
        "always_on_top": True
    },
    "pet": {
        "celebration_duration_sec": 5,
        "show_printer_name": True,
        "compact_mode": "most_progress"
    }
}


def cargar_config() -> dict:
    """Carga config.json con manejo de errores y defaults."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        # Merge con defaults
        config = DEFAULT_CONFIG.copy()
        for key, value in user_config.items():
            if isinstance(value, dict) and key in config:
                config[key].update(value)
            else:
                config[key] = value
        logger.info(f"Configuración cargada desde {CONFIG_PATH}")
        return config
    except FileNotFoundError:
        logger.warning(f"config.json no encontrado en {CONFIG_PATH}, usando defaults")
        return DEFAULT_CONFIG.copy()
    except json.JSONDecodeError as e:
        logger.error(f"config.json inválido: {e}, usando defaults")
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        logger.error(f"Error cargando config: {e}")
        return DEFAULT_CONFIG.copy()


def guardar_config(config: dict):
    """Guarda la configuración en config.json."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("Configuración guardada")
    except Exception as e:
        logger.error(f"Error guardando config: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# Panel de Configuración
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsPanel:
    """Panel de configuración para bambuPet usando tkinter."""

    def __init__(self, parent: tk.Tk, config: dict, on_save: callable):
        self.parent = parent
        self.config = config
        self.on_save = on_save
        self.window = None

    def abrir(self):
        """Abre la ventana de configuración."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        self.window = Toplevel(self.parent)
        self.window.title("⚙️ bambuPet — Configuración")
        self.window.geometry("400x500")
        self.window.resizable(False, False)
        self.window.configure(bg="#1e1e2e")

        self._crear_widgets()

    def _crear_widgets(self):
        """Crea los widgets del panel."""
        main_frame = tk.Frame(self.window, bg="#1e1e2e", padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Título
        tk.Label(
            main_frame, text="🐼 bambuPet",
            font=("Segoe UI", 18, "bold"),
            fg="#cdd6f4", bg="#1e1e2e"
        ).pack(pady=(0, 10))

        # ── MQTT ──
        self._seccion(main_frame, "📡 MQTT", [
            ("Intervalo de encuesta (sec):", "mqtt", "poll_interval_sec"),
            ("Delay de reconexión (sec):", "mqtt", "reconnect_delay_sec"),
        ])

        # ── Display ──
        self._seccion(main_frame, "🖥️ Pantalla", [
            ("Escala (0.5-2.0):", "display", "scale"),
            ("Opacidad (0.1-1.0):", "display", "opacity"),
            ("Siempre encima:", "display", "always_on_top"),
        ])

        # ── Impresoras ──
        tk.Label(
            main_frame, text="🖨️ Impresoras",
            font=("Segoe UI", 12, "bold"),
            fg="#89b4fa", bg="#1e1e2e"
        ).pack(anchor=tk.W, pady=(15, 5))

        printers = self.config.get("mqtt", {}).get("printers", [])
        if printers:
            for p in printers:
                texto = f"  • {p.get('name', 'Sin nombre')} @ {p.get('ip', 'N/A')}"
                tk.Label(
                    main_frame, text=texto,
                    font=("Segoe UI", 10),
                    fg="#a6adc8", bg="#1e1e2e"
                ).pack(anchor=tk.W)
        else:
            tk.Label(
                main_frame, text="  (No hay impresoras configuradas)",
                font=("Segoe UI", 10),
                fg="#6c7086", bg="#1e1e2e"
            ).pack(anchor=tk.W)

        # Botones
        btn_frame = tk.Frame(main_frame, bg="#1e1e2e")
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        tk.Button(
            btn_frame, text="💾 Guardar", command=self._guardar,
            font=("Segoe UI", 11), bg="#a6e3a1", fg="#1e1e2e",
            relief=tk.FLAT, padx=20, pady=8, cursor="hand2"
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        tk.Button(
            btn_frame, text="❌ Cancelar", command=self.window.destroy,
            font=("Segoe UI", 11), bg="#f38ba8", fg="#1e1e2e",
            relief=tk.FLAT, padx=20, pady=8, cursor="hand2"
        ).pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(5, 0))

    def _seccion(self, parent: tk.Frame, titulo: str, campos: list):
        """Crea una sección del formulario."""
        tk.Label(
            parent, text=titulo,
            font=("Segoe UI", 12, "bold"),
            fg="#89b4fa", bg="#1e1e2e"
        ).pack(anchor=tk.W, pady=(10, 5))

        for texto, seccion, key in campos:
            frame = tk.Frame(parent, bg="#1e1e2e")
            frame.pack(fill=tk.X, pady=2)

            tk.Label(
                frame, text=texto,
                font=("Segoe UI", 10),
                fg="#cdd6f4", bg="#1e1e2e", width=25, anchor=tk.W
            ).pack(side=tk.LEFT)

            var = tk.StringVar(value=str(self.config.get(seccion, {}).get(key, "")))
            entry = tk.Entry(
                frame, textvariable=var,
                font=("Segoe UI", 10),
                bg="#313244", fg="#cdd6f4",
                insertbackground="#cdd6f4",
                relief=tk.FLAT, width=15
            )
            entry.pack(side=tk.LEFT, padx=(10, 0))

            # Guardar referencia para lectura posterior
            setattr(self, f"_{seccion}_{key}", var)

    def _guardar(self):
        """Guarda los cambios y cierra."""
        try:
            # Actualizar valores
            for seccion, key in [
                ("mqtt", "poll_interval_sec"),
                ("mqtt", "reconnect_delay_sec"),
                ("display", "scale"),
                ("display", "opacity"),
            ]:
                var = getattr(self, f"_{seccion}_{key}", None)
                if var:
                    try:
                        self.config[seccion][key] = float(var.get())
                    except ValueError:
                        pass

            var_top = getattr(self, "_display_always_on_top", None)
            if var_top:
                self.config["display"]["always_on_top"] = var_top.get().lower() in ("true", "1", "yes")

            guardar_config(self.config)

            if self.on_save:
                self.on_save(self.config)

            self.window.destroy()
            logger.info("Configuración actualizada")

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self.window)


# ═══════════════════════════════════════════════════════════════════════════════
# Ventana del Pet (tkinter)
# ═══════════════════════════════════════════════════════════════════════════════

class PetWindow:
    """Ventana del pet interactivo con tkinter."""

    PET_SIZE = 156

    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        self.config = config
        self.printer_states: Dict[str, dict] = {}
        self.state_trackers: Dict[str, PrinterStateTracker] = {}
        self.expanded = False
        self.drag_data = {"x": 0, "y": 0, "dragging": False}

        self._configurar_ventana()
        self._crear_canvas()

    def _configurar_ventana(self):
        """Configura ventana transparente y frameless."""
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", self.config["display"]["always_on_top"])

        # Intentar transparencia de color (Windows)
        try:
            self.root.attributes("-transparentcolor", "#1e1e2e")
            self.bg_color = "#1e1e2e"
        except tk.TclError:
            self.bg_color = "#2d2d3d"

        scale = self.config["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)
        self.root.geometry(f"{size}x{size}")

        opacity = self.config["display"].get("opacity", 0.95)
        try:
            self.root.attributes("-alpha", opacity)
        except tk.TclError:
            pass

        self._posicionar_ventana()

    def _posicionar_ventana(self):
        """Posiciona en esquina inferior derecha."""
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        offset_x = self.config["display"].get("offset_x", 20)
        offset_y = self.config["display"].get("offset_y", 20)
        size = self.root.winfo_width()
        x = screen_w - size - offset_x
        y = screen_h - size - offset_y - 40  # Compensar taskbar
        self.root.geometry(f"+{x}+{y}")

    def _crear_canvas(self):
        """Crea el canvas dibuja el pet."""
        scale = self.config["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)

        self.canvas = tk.Canvas(
            self.root,
            width=size, height=size,
            bg=self.bg_color,
            highlightthickness=0,
            cursor="hand2"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Dibujar el pet
        self._dibujar_pet()

        # Eventos
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)  # Clic derecho para settings

    def _dibujar_pet(self):
        """Dibuja el pet (emoji de panda) en el canvas."""
        self.canvas.delete("all")

        scale = self.config["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)
        center = size // 2
        radio = size // 2 - 4

        # Círculo de fondo
        self.canvas.create_oval(
            center - radio, center - radio,
            center + radio, center + radio,
            fill="#1e1e2e", outline="#89b4fa", width=2
        )

        # Emoji de panda (o texto si no hay emoji)
        try:
            self.canvas.create_text(
                center, center,
                text="🐼",
                font=("Segoe UI Emoji", int(48 * scale)),
                anchor=tk.CENTER
            )
        except tk.TclError:
            # Fallback si no hay emoji
            self.canvas.create_text(
                center, center,
                text="PET",
                font=("Segoe UI", int(20 * scale), "bold"),
                fill="#89b4fa",
                anchor=tk.CENTER
            )

        # Indicador de estado (punto de color)
        status_color = self._get_status_color()
        dot_x = center + int(radio * 0.7)
        dot_y = center + int(radio * 0.7)
        self.canvas.create_oval(
            dot_x - 6, dot_y - 6,
            dot_x + 6, dot_y + 6,
            fill=status_color, outline=""
        )

        # Texto de progreso (si hay)
        if self.printer_states:
            summary = get_print_summary(self._get_enriched_states())
            if summary and summary != "Sin impresoras":
                self.canvas.create_text(
                    center, size - 8,
                    text=summary[:30],
                    font=("Segoe UI", int(9 * scale)),
                    fill="#a6adc8",
                    anchor=tk.S
                )

    def _get_status_color(self) -> str:
        """Retorna color según estado de impresoras."""
        states = self._get_enriched_states()
        if not states:
            return "#6c7086"  # Gris

        best_status = None
        priority = {"printing": 0, "paused": 1, "finished": 2, "preparing": 3, "idle": 4, "error": 5}
        best_priority = 99

        for state in states.values():
            status = state.get("status", "idle")
            p = priority.get(status, 99)
            if p < best_priority:
                best_priority = p
                best_status = status

        colors = {
            "printing": "#a6e3a1",
            "paused": "#f9e2af",
            "finished": "#89b4fa",
            "preparing": "#cba6f7",
            "idle": "#a6adc8",
            "error": "#f38ba8"
        }
        return colors.get(best_status, "#6c7086")

    def _get_enriched_states(self) -> Dict[str, dict]:
        """Retorna estados enriquecidos de todas las impresoras."""
        result = {}
        for serial, raw in self.printer_states.items():
            tracker = self.state_trackers.get(serial)
            if tracker:
                parsed = tracker.update(raw)
            else:
                parsed = parse_printer_status(raw)
                parsed["name"] = serial
            parsed["serial"] = serial
            result[serial] = parsed
        return result

    def actualizar_estado(self, serial: str, raw_data: dict):
        """Actualiza el estado de una impresora y redibuja."""
        self.printer_states[serial] = raw_data

        if serial not in self.state_trackers:
            config = self._get_printer_config(serial)
            name = config.get("name", serial) if config else serial
            self.state_trackers[serial] = PrinterStateTracker(name=name)

        # Redibujar en el hilo principal
        self.root.after(0, self._dibujar_pet)

    def _get_printer_config(self, serial: str) -> dict:
        """Obtiene configuración de una impresora por serial."""
        for p in self.config.get("mqtt", {}).get("printers", []):
            if p.get("serial") == serial:
                return p
        return {}

    # ── Interacciones ──

    def _on_click(self, event):
        """Inicio de posible drag o click."""
        self.drag_data["x"] = event.x_root
        self.drag_data["y"] = event.y_root
        self.drag_data["dragging"] = False
        self.drag_data["start_x"] = event.x_root
        self.drag_data["start_y"] = event.y_root

    def _on_drag(self, event):
        """Movimiento durante drag."""
        dx = abs(event.x_root - self.drag_data["start_x"])
        dy = abs(event.y_root - self.drag_data["start_y"])
        if dx > 3 or dy > 3:
            self.drag_data["dragging"] = True

        if self.drag_data["dragging"]:
            x = self.root.winfo_x() + (event.x_root - self.drag_data["x"])
            y = self.root.winfo_y() + (event.y_root - self.drag_data["y"])
            self.root.geometry(f"+{x}+{y}")
            self.drag_data["x"] = event.x_root
            self.drag_data["y"] = event.y_root

    def _on_release(self, event):
        """Fin de click/drag."""
        if not self.drag_data["dragging"]:
            # Fue click, no drag → abrir settings
            self._abrir_settings()
        self.drag_data["dragging"] = False

    def _on_right_click(self, event):
        """Clic derecho → menú contextual."""
        menu = tk.Menu(self.root, tearoff=0, bg="#1e1e2e", fg="#cdd6f4")
        menu.add_command(label="⚙️ Configuración", command=self._abrir_settings)
        menu.add_command(label="🔄 Reconectar", command=self._reconectar)
        menu.add_separator()
        menu.add_command(label="❌ Salir", command=self.root.quit)
        menu.tk_popup(event.x_root, event.y_root)

    def _abrir_settings(self):
        """Abre el panel de configuración."""
        if hasattr(self, '_on_settings_save'):
            self._on_settings_save()

    def set_settings_callback(self, callback):
        """Establece callback para abrir settings."""
        self._on_settings_save = callback

    def _reconectar(self):
        """Reconectar MQTT."""
        logger.info("Reconexión solicitada")
        # El callback de reconexión se maneja en BambuPetApp


# ═══════════════════════════════════════════════════════════════════════════════
# Aplicación Principal
# ═══════════════════════════════════════════════════════════════════════════════

class BambuPetApp:
    """
    Entry point principal de bambuPet.
    Integra parser.py + mqtt_manager.py en una interfaz tkinter.
    """

    def __init__(self):
        """Inicializa la aplicación."""
        self.root = None
        self.config = {}
        self.mqtt_manager: Optional[MQTTManager] = None
        self.pet_window: Optional[PetWindow] = None
        self.settings_panel: Optional[SettingsPanel] = None
        self._shutdown = False

        # Cargar configuración
        self.config = cargar_config()

        # Validar configuración mínima
        printers = self.config.get("mqtt", {}).get("printers", [])
        if not printers:
            logger.warning("No hay impresoras configuradas en config.json")
            logger.info("Configura al menos una impresora con: name, ip, serial, access_code")

    def run(self):
        """Inicia la aplicación y el mainloop."""
        try:
            self._crear_ui()
            self._iniciar_mqtt()

            logger.info("🐼 bambuPet iniciado")
            logger.info("   Click izquierdo: configuración")
            logger.info("   Clic derecho: menú")
            logger.info("   Arrastra para mover")

            self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
            self.root.mainloop()

        except Exception as e:
            logger.error(f"Error fatal en run(): {e}")
            self.shutdown()
            raise

    def shutdown(self):
        """Cierre limpio de MQTT y UI."""
        if self._shutdown:
            return
        self._shutdown = True

        logger.info("Cerrando bambuPet...")

        if self.mqtt_manager:
            try:
                self.mqtt_manager.stop_all()
                logger.info("MQTT desconectado")
            except Exception as e:
                logger.error(f"Error desconectando MQTT: {e}")

        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass

        logger.info("bambuPet cerrado correctamente")

    # ── Inicialización ──

    def _crear_ui(self):
        """Crea la interfaz de usuario."""
        self.root = tk.Tk()
        self.root.withdraw()  # Ocultar root principal

        # Crear ventana del pet
        self.pet_window = PetWindow(self.root, self.config)

        # Crear panel de settings
        self.settings_panel = SettingsPanel(
            self.root,
            self.config,
            on_save=self._on_config_saved
        )

        # Conectar callbacks
        self.pet_window.set_settings_callback(
            lambda: self.settings_panel.abrir()
        )

    def _iniciar_mqtt(self):
        """Inicia conexiones MQTT."""
        printers = self.config.get("mqtt", {}).get("printers", [])
        if not printers:
            logger.warning("No hay impresoras para conectar")
            return

        # Validar impresoras
        required_keys = {"name", "ip", "serial", "access_code"}
        valid_printers = []
        for p in printers:
            missing = required_keys - set(p.keys())
            if missing:
                logger.warning(f"Impresora inválida, faltan {missing}: {p.get('name', '?')}")
            else:
                valid_printers.append(p)

        if not valid_printers:
            logger.error("No hay impresoras válidas configuradas")
            return

        # Crear manager
        self.mqtt_manager = MQTTManager(on_state_change=self._on_mqtt_message)

        for printer_conf in valid_printers:
            self.mqtt_manager.add_printer(printer_conf)

        # Conectar todas
        self.mqtt_manager.start_all()

        # Timer para pushall periódico
        interval = self.config.get("mqtt", {}).get("poll_interval_sec", 10)
        self._programar_pushall(interval)

        # Timer para reconexión
        reconnect_delay = self.config.get("mqtt", {}).get("reconnect_delay_sec", 5)
        self._reconnect_attempts = {}
        self._programar_reconexion(reconnect_delay)

    # ── Callbacks MQTT ──

    def _on_mqtt_message(self, serial: str, raw_data: dict):
        """Mensaje MQTT recibido — se ejecuta en hilo de paho."""
        if self._shutdown:
            return

        # Actualizar UI de forma thread-safe via after()
        try:
            if self.pet_window and self.root:
                self.pet_window.actualizar_estado(serial, raw_data)
        except Exception as e:
            logger.error(f"Error actualizando UI: {e}")

    def _on_config_saved(self, new_config: dict):
        """Callback cuando se guarda configuración."""
        logger.info("Nueva configuración aplicada")
        self.config = new_config

        # Aplicar cambios de display
        if self.pet_window:
            self.pet_window.config = new_config
            self.pet_window._configurar_ventana()

        # Reconectar MQTT si cambiaron impresoras
        if self.mqtt_manager:
            self.mqtt_manager.stop_all()
        self._iniciar_mqtt()

    # ── Timers ──

    def _programar_pushall(self, interval_sec: int):
        """Programa envío periódico de pushall."""
        if self._shutdown:
            return

        if self.mqtt_manager:
            self.mqtt_manager.request_all_status()

        # Reprogramar
        self.root.after(interval_sec * 1000, lambda: self._programar_pushall(interval_sec))

    def _programar_reconexion(self, delay_sec: int):
        """Verifica y reconecta impresoras desconectadas."""
        if self._shutdown:
            return

        if self.mqtt_manager:
            for serial, client in self.mqtt_manager.clients.items():
                if not client.connected:
                    attempts = self._reconnect_attempts.get(serial, 0)
                    backoff = min(delay_sec * (2 ** attempts), 60)

                    import time
                    last_attempt = getattr(client, '_last_reconnect_attempt', 0)
                    if time.time() - last_attempt >= backoff:
                        logger.info(f"🔄 Reconectando a {serial} (intento {attempts + 1})...")
                        try:
                            client._last_reconnect_attempt = time.time()
                            client.connect()
                            self._reconnect_attempts[serial] = attempts + 1
                        except Exception as e:
                            logger.error(f"Error reconectando a {serial}: {e}")
                            self._reconnect_attempts[serial] = attempts + 1
                else:
                    self._reconnect_attempts.pop(serial, None)

        # Reprogramar
        self.root.after(delay_sec * 1000, lambda: self._programar_reconexion(delay_sec))


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        app = BambuPetApp()
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado")
    except Exception as e:
        logger.error(f"Error no manejado: {e}")
        # Mostrar error en mensaje si no hay UI
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("bambuPet Error", f"Error al iniciar:\n\n{e}")
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
