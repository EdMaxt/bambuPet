"""
bambuPet v0.4.0 - Entry point con CustomTkinter
Widget desktop para monitoreo de impresoras BambuLab
"""

import sys
import os
import json
import logging
import customtkinter as ctk
from typing import Dict, Optional

# Asegurar directorio del proyecto en path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from parser import PrinterStateTracker, get_print_summary
from mqtt_manager import MQTTManager
from mock_rocky import MockRocky

# CustomTkinter appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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


# ═══════════════════════════════════════════════════════════════════════════════
# Widget Principal
# ═══════════════════════════════════════════════════════════════════════════════

class BambuPetWidget(ctk.CTk):
    """Widget principal de bambuPet."""

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
        self.geometry(f"{size}x{size}")
        self.resizable(False, False)

        if self.config_data["display"].get("always_on_top", True):
            self.attributes("-topmost", True)

        opacity = self.config_data["display"].get("opacity", 0.95)
        self.attributes("-alpha", opacity)

        if sys.platform == "win32":
            self.overrideredirect(True)

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
        scale = self.config_data["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)

        self.main_frame = ctk.CTkFrame(
            self, width=size, height=size,
            corner_radius=size // 2,
            fg_color="#1e1e2e", border_width=2, border_color="#00e5ff"
        )
        self.main_frame.pack_propagate(False)
        self.main_frame.pack(expand=True, fill="both")

        self.canvas = ctk.CTkCanvas(
            self.main_frame, width=size, height=size,
            bg="#1e1e2e", highlightthickness=0
        )
        self.canvas.pack(expand=True, fill="both", padx=10, pady=10)

        self._dibujar_pet()

        for widget in [self, self.main_frame, self.canvas]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<ButtonRelease-1>", self._on_release)
            widget.bind("<Button-3>", self._on_right_click)

    def _dibujar_pet(self):
        self.canvas.delete("all")
        scale = self.config_data["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)
        center = size // 2

        summary = get_print_summary(self._get_enriched_states())
        progress = summary.get("progress", 0) if summary else 0
        status = summary.get("status", "idle") if summary else "idle"
        name = summary.get("name", "") if summary else ""

        status_colors = {
            "printing": "#00e5ff", "paused": "#ffd93d", "done": "#6bcb77",
            "preparing": "#cba6f7", "idle": "#6c7086", "error": "#f38ba8"
        }
        color = status_colors.get(status, "#6c7086")

        self.canvas.create_oval(15, 15, size - 15, size - 15, fill="#313244", outline=color, width=3)

        if progress > 0:
            bbox = (20, 20, size - 20, size - 20)
            extent = (progress / 100) * 360
            self.canvas.create_arc(bbox, start=-90, extent=extent, outline=color, width=4, style="arc")

        if status == "printing":
            text = f"{progress}%"
            font_size = int(28 * scale)
        elif status == "done":
            text = "✓"
            font_size = int(36 * scale)
        elif status == "error":
            text = "⚠"
            font_size = int(32 * scale)
        elif status == "paused":
            text = "⏸"
            font_size = int(28 * scale)
        else:
            text = "🐼"
            font_size = int(32 * scale)

        self.canvas.create_text(center, center, text=text, font=("Segoe UI Emoji", font_size), fill=color if status != "idle" else "#cdd6f4")

        if name and self.config_data["pet"].get("show_printer_name", True):
            self.canvas.create_text(center, size - 12, text=name[:12], font=("Segoe UI", int(9 * scale)), fill="#a0a0a0")

        # Indicador de modo
        if self._mock:
            self.canvas.create_text(size - 30, 15, text="DEMO", font=("Segoe UI", int(7 * scale), "bold"), fill="#ffd93d")
        elif self.mqtt_manager and self.mqtt_manager.connected_count == 0:
            self.canvas.create_text(size - 25, 15, text="OFF", font=("Segoe UI", int(7 * scale), "bold"), fill="#f38ba8")

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

    def _on_click(self, event):
        self._drag_data["x"] = event.x_root
        self._drag_data["y"] = event.y_root
        self._drag_data["dragging"] = False
        self._drag_data["start_x"] = event.x_root
        self._drag_data["start_y"] = event.y_root

    def _on_drag(self, event):
        dx = abs(event.x_root - self._drag_data["start_x"])
        dy = abs(event.y_root - self._drag_data["start_y"])
        if dx > 3 or dy > 3:
            self._drag_data["dragging"] = True
        if self._drag_data["dragging"]:
            x = self.winfo_x() + (event.x_root - self._drag_data["x"])
            y = self.winfo_y() + (event.y_root - self._drag_data["y"])
            self.geometry(f"+{x}+{y}")
            self._drag_data["x"] = event.x_root
            self._drag_data["y"] = event.y_root

    def _on_release(self, event):
        if not self._drag_data["dragging"]:
            self._abrir_settings()
        self._drag_data["dragging"] = False

    def _on_right_click(self, event):
        menu = ctk.CTkToplevel(self)
        menu.overrideredirect(True)
        menu.geometry(f"+{event.x_root}+{event.y_root}")
        frame = ctk.CTkFrame(menu, fg_color="#1e1e2e", corner_radius=8)
        frame.pack()
        for text, cmd in [("⚙️ Configuración", self._abrir_settings), ("🔄 Reconectar", lambda: None), ("❌ Salir", self.destroy)]:
            ctk.CTkButton(frame, text=text, command=lambda c=cmd: (menu.destroy(), c()), fg_color="transparent", hover_color="#313244", text_color="#cdd6f4", anchor="w", height=30).pack(fill="x", padx=5, pady=2)
        menu.bind("<FocusOut>", lambda e: menu.destroy())
        menu.focus_force()

    def _abrir_settings(self):
        SettingsWindow(self, self.config_data, on_save=self._aplicar_config)

    def _aplicar_config(self, new_config):
        self.config_data = new_config
        self._configurar_ventana()
        self._dibujar_pet()

    def _iniciar_mqtt(self):
        printers = self.config_data.get("mqtt", {}).get("printers", [])
        if not printers:
            self._activar_mock()
            return
        self.mqtt_manager = MQTTManager(on_state_change=self.actualizar_estado)
        for p in printers:
            self.mqtt_manager.add_printer(p)
        self.mqtt_manager.start_all()
        self.after(8000, self._verificar_conexion)

    def _verificar_conexion(self):
        if self.mqtt_manager and self.mqtt_manager.connected_count == 0:
            logger.warning("Sin conexión → DEMO")
            self._activar_mock()

    def _activar_mock(self):
        self._mock = MockRocky(on_message=self.actualizar_estado)
        self._mock.start()
        self._dibujar_pet()


# ═══════════════════════════════════════════════════════════════════════════════
# Panel de Configuración
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, config: dict, on_save=None):
        super().__init__(parent)
        self.config_data = config
        self.on_save = on_save

        self.title("bambuPet - Config")
        self.geometry("360x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 180
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 190
        self.geometry(f"+{x}+{y}")

        main = ctk.CTkFrame(self, fg_color="#1e1e2e")
        main.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(main, text="🐼 bambuPet", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(10, 15))

        # Escala
        ctk.CTkLabel(main, text="Tamaño", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=10)
        self.scale_var = ctk.DoubleVar(value=config["display"]["scale"])
        self.scale_label = ctk.CTkLabel(main, text=f"{int(config['display']['scale'] * 100)}%", font=ctk.CTkFont(size=12))
        self.scale_label.pack(anchor="e", padx=10)
        ctk.CTkSlider(main, from_=0.5, to=2.0, variable=self.scale_var, command=lambda v: self.scale_label.configure(text=f"{int(v * 100)}%"), button_color="#00e5ff", progress_color="#00e5ff").pack(fill="x", padx=10, pady=(0, 10))

        # Opacidad
        ctk.CTkLabel(main, text="Opacidad", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=10)
        self.opacity_var = ctk.DoubleVar(value=config["display"]["opacity"])
        self.opacity_label = ctk.CTkLabel(main, text=f"{int(config['display']['opacity'] * 100)}%", font=ctk.CTkFont(size=12))
        self.opacity_label.pack(anchor="e", padx=10)
        ctk.CTkSlider(main, from_=0.2, to=1.0, variable=self.opacity_var, command=lambda v: self.opacity_label.configure(text=f"{int(v * 100)}%"), button_color="#00e5ff", progress_color="#00e5ff").pack(fill="x", padx=10, pady=(0, 10))

        # Siempre encima
        self.top_var = ctk.BooleanVar(value=config["display"]["always_on_top"])
        ctk.CTkCheckBox(main, text="Siempre encima", variable=self.top_var, checkbox_height=20, fg_color="#00e5ff", hover_color="#00e5ff").pack(anchor="w", padx=10, pady=(5, 10))

        # Impresoras
        ctk.CTkLabel(main, text="Impresoras:", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=10)
        for p in config.get("mqtt", {}).get("printers", []):
            ctk.CTkLabel(main, text=f"  • {p.get('name', '?')} @ {p.get('ip', '?')}", font=ctk.CTkFont(size=11), text_color="#a0a0a0").pack(anchor="w", padx=10)

        # Botones
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkButton(btn_frame, text="Guardar", command=self._guardar, fg_color="#00e5ff", hover_color="#00b8d4", text_color="#000000", font=ctk.CTkFont(size=13, weight="bold"), height=36).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="Cancelar", command=self.destroy, fg_color="#f38ba8", hover_color="#e06c75", text_color="#000000", font=ctk.CTkFont(size=13), height=36).pack(side="right", expand=True, fill="x", padx=(5, 0))

    def _guardar(self):
        self.config_data["display"]["scale"] = self.scale_var.get()
        self.config_data["display"]["opacity"] = self.opacity_var.get()
        self.config_data["display"]["always_on_top"] = self.top_var.get()
        guardar_config(self.config_data)
        if self.on_save:
            self.on_save(self.config_data)
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

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
