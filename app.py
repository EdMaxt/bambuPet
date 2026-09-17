"""
bambuPet v0.6.0 - Tkinter nativo + CTk para settings
Widget desktop para monitoreo de impresoras BambuLab
"""

import sys
import os
import json
import logging
import threading
import tkinter as tk
from typing import Dict, Optional

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from parser import PrinterStateTracker, get_print_summary
from mqtt_manager import MQTTManager
from mock_rocky import MockRocky

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
DEFAULT_CONFIG = {
    "mqtt": {"poll_interval_sec": 10, "reconnect_delay_sec": 5, "printers": []},
    "display": {"position": "bottom-right", "offset_x": 20, "offset_y": 20, "scale": 1.0, "opacity": 0.95, "always_on_top": True},
    "pet": {"celebration_duration_sec": 5, "show_printer_name": True, "compact_mode": "most_progress"}
}

def cargar_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        config = DEFAULT_CONFIG.copy()
        for key, value in user_config.items():
            if isinstance(value, dict) and key in config:
                config[key].update(value)
            else:
                config[key] = value
        return config
    except Exception:
        return DEFAULT_CONFIG.copy()

def guardar_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class BambuPetWidget(tk.Tk):
    """Widget principal de bambuPet - Tkinter nativo."""

    PET_SIZE = 156

    def __init__(self):
        super().__init__()
        self.config_data = cargar_config()
        self.printer_states: Dict[str, dict] = {}
        self.state_trackers: Dict[str, PrinterStateTracker] = {}
        self.mqtt_manager: Optional[MQTTManager] = None
        self._mock: Optional[MockRocky] = None
        self._drag_data = {"x": 0, "y": 0, "dragging": False}
        
        self._configurar_ventana()
        self._crear_interfaz()
        self._iniciar_mqtt()

    def _configurar_ventana(self):
        self.title("bambuPet")
        scale = self.config_data["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)
        self.geometry(f"{size}x{size}+0+0")
        self.resizable(False, False)
        self.overrideredirect(True)
        
        if self.config_data["display"].get("always_on_top", True):
            self.attributes("-topmost", True)
        
        opacity = self.config_data["display"].get("opacity", 0.95)
        self.attributes("-alpha", opacity)
        
        self._posicionar_ventana()

    def _posicionar_ventana(self):
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        offset_x = self.config_data["display"].get("offset_x", 20)
        offset_y = self.config_data["display"].get("offset_y", 20)
        size = self.winfo_width()
        x = screen_w - size - offset_x
        y = screen_h - size - offset_y - 50
        self.geometry(f"+{x}+{y}")

    def _crear_interfaz(self):
        for w in self.winfo_children():
            w.destroy()
        
        scale = self.config_data["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)
        
        bg_color = "#1e1e2e"
        fg_color = "#cdd6f4"
        accent = "#00e5ff"

        # Frame circular
        self.canvas = tk.Canvas(
            self, width=size, height=size,
            bg=bg_color, highlightthickness=0
        )
        self.canvas.pack(expand=True, fill="both")

        # Info label
        self.info_label = tk.Label(
            self, text="", font=("Segoe UI", max(8, int(9 * scale))),
            bg=bg_color, fg="#a0a0a0", wraplength=size-20
        )
        self.info_label.pack(side="bottom", pady=(0, 15))

        # Boton settings
        self.btn_settings = tk.Button(
            self, text="⚙️", font=("Segoe UI Emoji", 14),
            bg="#313244", fg=fg_color, activebackground="#45475a",
            activeforeground=fg_color, bd=0, padx=4, pady=2,
            command=self._mostrar_menu
        )
        self.btn_settings.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)

        # Bindings
        for widget in [self, self.canvas, self.info_label]:
            widget.bind("<Button-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)
            widget.bind("<Button-3>", self._mostrar_menu)

        self._dibujar_pet()

    def _dibujar_pet(self):
        self.canvas.delete("all")
        scale = self.config_data["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)
        cx, cy = size // 2, size // 2
        r = size // 2 - 15

        states = self._get_enriched_states()
        summary = get_print_summary(states) if states else None
        
        progress = 0
        status = "idle"
        name = ""

        if isinstance(summary, dict):
            progress = summary.get("progress", 0)
            status = summary.get("status", "idle")
            name = summary.get("name", "")

        status_colors = {
            "printing": "#00e5ff", "paused": "#ffd93d", "done": "#6bcb77",
            "preparing": "#cba6f7", "idle": "#6c7086", "error": "#f38ba8",
            "finished": "#6bcb77"
        }
        color = status_colors.get(status, "#6c7086")

        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#313244", outline=color, width=3)

        if progress > 0 and status == "printing":
            bbox = (cx-r+5, cy-r+5, cx+r-5, cy+r-5)
            extent = (progress / 100) * 360
            self.canvas.create_arc(bbox, start=-90, extent=extent, outline=color, width=4, style="arc")

        if status == "printing":
            text = f"{progress}%"
            fs = int(24 * scale)
        elif status in ("done", "finished"):
            text = "✓"
            fs = int(32 * scale)
        elif status == "error":
            text = "⚠"
            fs = int(28 * scale)
        elif status == "paused":
            text = "⏸"
            fs = int(24 * scale)
        else:
            text = "🐼"
            fs = int(28 * scale)

        self.canvas.create_text(cx, cy, text=text, font=("Segoe UI Emoji", fs), fill=color if status != "idle" else "#cdd6f4")

        # Connection indicator
        if self._mock:
            self.canvas.create_text(cx + r - 10, cy - r + 10, text="DEMO", font=("Segoe UI", int(7 * scale), "bold"), fill="#ffd93d")
        elif self.mqtt_manager and self.mqtt_manager.connected_count > 0:
            self.canvas.create_oval(cx + r - 15, cy - r + 5, cx + r - 5, cy - r + 15, fill="#6bcb77", outline="")
        else:
            self.canvas.create_oval(cx + r - 15, cy - r + 5, cx + r - 5, cy - r + 15, fill="#f38ba8", outline="")

        self._actualizar_info_label(states, scale)

    def _actualizar_info_label(self, states: Dict, scale: float):
        if not states:
            self.info_label.configure(text="Sin datos")
            return
        
        priority = {"printing": 0, "paused": 1, "finished": 2, "preparing": 3, "idle": 4, "error": 5}
        best_state = None
        best_p = 999
        
        for state in states.values():
            p = priority.get(state.get("status", "idle"), 99)
            if p < best_p:
                best_p = p
                best_state = state
        
        if best_state:
            name = best_state.get("name", "")[:12]
            status = best_state.get("status", "idle")
            progress = best_state.get("progress", 0)
            
            if status == "printing":
                info = f"{name}: {progress}%"
            elif status == "paused":
                info = f"{name}: Pausado"
            elif status in ("done", "finished"):
                info = f"{name}: Listo"
            elif status == "error":
                info = f"{name}: Error"
            else:
                info = f"{name}: En espera"
            
            self.info_label.configure(text=info)

    def _get_enriched_states(self) -> Dict[str, dict]:
        result = {}
        for serial, raw in self.printer_states.items():
            tracker = self.state_trackers.get(serial)
            if tracker:
                parsed = tracker.update(raw)
            else:
                from parser import parse_printer_status
                parsed = parse_printer_status(raw)
                parsed["name"] = serial
            result[serial] = parsed
        return result

    def actualizar_estado(self, serial: str, raw_data: dict):
        self.printer_states[serial] = raw_data
        if serial not in self.state_trackers:
            name = "Rocky"
            for p in self.config_data.get("mqtt", {}).get("printers", []):
                if p.get("serial") == serial:
                    name = p.get("name", serial)
            self.state_trackers[serial] = PrinterStateTracker(name=name)
        self.after(0, self._dibujar_pet)

    def _on_drag_start(self, event):
        if event.widget == self.btn_settings:
            return
        self._drag_data["x"] = event.x_root
        self._drag_data["y"] = event.y_root
        self._drag_data["dragging"] = False

    def _on_drag_motion(self, event):
        if event.widget == self.btn_settings:
            return
        dx = abs(event.x_root - self._drag_data["x"])
        dy = abs(event.y_root - self._drag_data["y"])
        if dx > 3 or dy > 3:
            self._drag_data["dragging"] = True
        if self._drag_data["dragging"]:
            new_x = self.winfo_x() + (event.x_root - self._drag_data["x"])
            new_y = self.winfo_y() + (event.y_root - self._drag_data["y"])
            self.geometry(f"+{new_x}+{new_y}")
            self._drag_data["x"] = event.x_root
            self._drag_data["y"] = event.y_root

    def _on_drag_end(self, event):
        self._drag_data["dragging"] = False

    def _mostrar_menu(self, event=None):
        menu = tk.Menu(self, tearoff=0, bg="#1e1e2e", fg="#cdd6f4",
                       activebackground="#313244", activeforeground="#cdd6f4")
        menu.add_command(label="⚙️ Configuración", command=self._abrir_settings)
        menu.add_command(label="🔄 Reconectar", command=self._reconectar)
        menu.add_command(label="📋 Info impresora", command=self._mostrar_info)
        menu.add_separator()
        menu.add_command(label="❌ Salir", command=self._salir)
        
        if event:
            menu.tk_popup(event.x_root, event.y_root)
        else:
            x = self.btn_settings.winfo_rootx()
            y = self.btn_settings.winfo_rooty() + 30
            menu.tk_popup(x, y)

    def _abrir_settings(self):
        SettingsWindow(self, self.config_data, on_save=self._aplicar_config)

    def _aplicar_config(self, new_config):
        self.config_data = new_config
        self._configurar_ventana()
        self._crear_interfaz()

    def _reconectar(self):
        if self.mqtt_manager:
            self.mqtt_manager.stop_all()
        self._iniciar_mqtt()

    def _mostrar_info(self):
        import customtkinter as ctk
        ctk.set_appearance_mode("dark")
        win = ctk.CTkToplevel(self)
        win.title("Info Impresora")
        win.geometry("300x250")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        
        main = ctk.CTkFrame(win, fg_color="#1e1e2e")
        main.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(main, text="🖨️ Estado de Impresora", font=ctk.CTkFont(16, "bold"), text_color="#00e5ff").pack(pady=(5, 10))
        
        states = self._get_enriched_states()
        if not states:
            ctk.CTkLabel(main, text="Sin datos de impresora", font=ctk.CTkFont(size=12), text_color="#a0a0a0").pack(expand=True)
        else:
            for state in states.values():
                info = f"Nombre: {state.get('name', '?')}\nEstado: {state.get('status', '?')}\nProgreso: {state.get('progress', 0)}%"
                ctk.CTkLabel(main, text=info, font=ctk.CTkFont(size=11), text_color="#cdd6f4", justify="left").pack(anchor="w", padx=10, pady=5)
        
        ctk.CTkButton(main, text="Cerrar", command=win.destroy, fg_color="#00e5ff", text_color="#000000", height=32).pack(side="bottom", fill="x", pady=(10, 0))

    def _salir(self):
        if self._mock:
            self._mock.stop()
        if self.mqtt_manager:
            self.mqtt_manager.stop_all()
        self.destroy()

    def _activar_mock(self):
        self._mock = MockRocky(on_message=self.actualizar_estado)
        self._mock.start()
        self._dibujar_pet()

    def _iniciar_mqtt(self):
        printers = self.config_data.get("mqtt", {}).get("printers", [])
        if not printers:
            self._activar_mock()
            return
        
        def _connect():
            self.mqtt_manager = MQTTManager(on_state_change=self.actualizar_estado)
            for p in printers:
                self.mqtt_manager.add_printer(p)
            self.mqtt_manager.start_all()
            import time
            time.sleep(6)
            if self.mqtt_manager.connected_count == 0:
                logger.warning("Sin conexión → DEMO")
                self._activar_mock()
            else:
                logger.info(f"✅ {self.mqtt_manager.connected_count} conectada(s)")
        
        threading.Thread(target=_connect, daemon=True).start()


class SettingsWindow(tk.Toplevel):
    """Ventana de configuración con Tkinter nativo."""

    def __init__(self, parent, config: dict, on_save=None):
        super().__init__(parent)
        self.config_data = config
        self.on_save = on_save
        self.parent = parent

        self.title("bambuPet - Config")
        self.geometry("350x400")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")
        self.attributes("-topmost", True)

        # Centrar
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 175
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 200
        self.geometry(f"+{x}+{y}")

        # Título
        tk.Label(self, text="🐼 bambuPet", font=("Segoe UI", 20, "bold"), bg="#1e1e2e", fg="#00e5ff").pack(pady=(15, 5))
        tk.Label(self, text="Configuración del widget", font=("Segoe UI", 11), bg="#1e1e2e", fg="#a0a0a0").pack(pady=(0, 15))

        # Scale
        scale_frame = tk.Frame(self, bg="#1e1e2e")
        scale_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(scale_frame, text="📐 Tamaño", font=("Segoe UI", 12, "bold"), bg="#1e1e2e", fg="#cdd6f4").pack(side="left")
        self.scale_label = tk.Label(scale_frame, text=f"{int(config['display']['scale'] * 100)}%", font=("Segoe UI", 11), bg="#1e1e2e", fg="#00e5ff")
        self.scale_label.pack(side="right")
        
        self.scale_var = tk.DoubleVar(value=config["display"]["scale"])
        scale_slider = tk.Scale(
            self, from_=0.5, to=2.0, variable=self.scale_var,
            orient="horizontal", bg="#1e1e2e", fg="#cdd6f4",
            troughcolor="#313244", highlightthickness=0,
            sliderrelief="flat", length=200,
            command=self._on_scale_change
        )
        scale_slider.pack(fill="x", padx=20)

        # Opacity
        opacity_frame = tk.Frame(self, bg="#1e1e2e")
        opacity_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(opacity_frame, text="👁 Opacidad", font=("Segoe UI", 12, "bold"), bg="#1e1e2e", fg="#cdd6f4").pack(side="left")
        self.opacity_label = tk.Label(opacity_frame, text=f"{int(config['display']['opacity'] * 100)}%", font=("Segoe UI", 11), bg="#1e1e2e", fg="#00e5ff")
        self.opacity_label.pack(side="right")
        
        self.opacity_var = tk.DoubleVar(value=config["display"]["opacity"])
        opacity_slider = tk.Scale(
            self, from_=0.2, to=1.0, variable=self.opacity_var,
            orient="horizontal", bg="#1e1e2e", fg="#cdd6f4",
            troughcolor="#313244", highlightthickness=0,
            sliderrelief="flat", length=200,
            command=self._on_opacity_change
        )
        opacity_slider.pack(fill="x", padx=20)

        # Always on top
        self.top_var = tk.BooleanVar(value=config["display"]["always_on_top"])
        tk.Checkbutton(self, text="Siempre encima", variable=self.top_var,
                      bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244",
                      activebackground="#1e1e2e", activeforeground="#cdd6f4",
                      font=("Segoe UI", 11)).pack(anchor="w", padx=20, pady=(10, 5))

        # Printers
        tk.Label(self, text="🖨 Impresoras:", font=("Segoe UI", 12, "bold"), bg="#1e1e2e", fg="#cdd6f4").pack(anchor="w", padx=20, pady=(10, 5))
        for p in config.get("mqtt", {}).get("printers", []):
            tk.Label(self, text=f"  • {p.get('name', '?')} @ {p.get('ip', '?')}", font=("Segoe UI", 10), bg="#1e1e2e", fg="#a0a0a0").pack(anchor="w", padx=30)

        # Buttons
        btn_frame = tk.Frame(self, bg="#1e1e2e")
        btn_frame.pack(fill="x", padx=20, pady=(15, 5))
        tk.Button(btn_frame, text="💾 Guardar", command=self._guardar, bg="#00e5ff", fg="#000000",
                 font=("Segoe UI", 12, "bold"), bd=0, padx=20, pady=8,
                 activebackground="#00b8d4", cursor="hand2").pack(side="left", expand=True, fill="x", padx=(0, 5))
        tk.Button(btn_frame, text="Cancelar", command=self.destroy, bg="#f38ba8", fg="#000000",
                 font=("Segoe UI", 12), bd=0, padx=20, pady=8,
                 activebackground="#e06c75", cursor="hand2").pack(side="right", expand=True, fill="x", padx=(5, 0))

    def _on_scale_change(self, value):
        val = float(value)
        self.scale_label.configure(text=f"{int(val * 100)}%")
        self.config_data["display"]["scale"] = val
        self.parent.config_data["display"]["scale"] = val
        self.parent._configurar_ventana()
        self.parent._crear_interfaz()

    def _on_opacity_change(self, value):
        val = float(value)
        self.opacity_label.configure(text=f"{int(val * 100)}%")
        self.parent.attributes("-alpha", val)

    def _guardar(self):
        self.config_data["display"]["scale"] = self.scale_var.get()
        self.config_data["display"]["opacity"] = self.opacity_var.get()
        self.config_data["display"]["always_on_top"] = self.top_var.get()
        guardar_config(self.config_data)
        if self.on_save:
            self.on_save(self.config_data)
        self.destroy()


def main():
    try:
        app = BambuPetWidget()
        logger.info("🐼 bambuPet iniciado")
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
