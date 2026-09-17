"""
bambuPet v0.5.0 - Entry point con CustomTkinter
Widget desktop para monitoreo de impresoras BambuLab
"""

import sys
import os
import json
import logging
import threading
import customtkinter as ctk
from typing import Dict, Optional

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from parser import PrinterStateTracker, get_print_summary
from mqtt_manager import MQTTManager
from mock_rocky import MockRocky

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

class BambuPetWidget(ctk.CTk):
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
        for w in self.winfo_children():
            w.destroy()
        
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
            self.main_frame, width=size - 20, height=size - 40,
            bg="#1e1e2e", highlightthickness=0
        )
        self.canvas.pack(expand=True, fill="both", padx=10, pady=10)

        self.info_label = ctk.CTkLabel(
            self.main_frame, text="",
            font=ctk.CTkFont(size=max(8, int(9 * scale))),
            text_color="#a0a0a0",
            wraplength=size - 30,
            justify="center"
        )
        self.info_label.pack(side="bottom", pady=(0, 15))

        self.btn_settings = ctk.CTkButton(
            self.main_frame, text="⚙️", width=28, height=28,
            corner_radius=14, fg_color="#313244", hover_color="#45475a",
            text_color="#cdd6f4", font=ctk.CTkFont(size=14),
            command=self._mostrar_menu_contextual
        )
        self.btn_settings.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)

        for widget in [self, self.main_frame, self.canvas, self.info_label]:
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)
            widget.bind("<Button-3>", self._mostrar_menu_contextual)

        self._dibujar_pet()

    def _dibujar_pet(self):
        try:
            self.canvas.delete("all")
        except Exception:
            return

        scale = self.config_data["display"].get("scale", 1.0)
        size = int(self.PET_SIZE * scale)
        center_x = (size - 20) // 2
        center_y = (size - 40) // 2

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

        margin = 12
        self.canvas.create_oval(
            margin, margin, size - 20 - margin, size - 40 - margin,
            fill="#313244", outline=color, width=3
        )

        if progress > 0 and status == "printing":
            bbox = (margin + 5, margin + 5, size - 20 - margin - 5, size - 40 - margin - 5)
            extent = (progress / 100) * 360
            self.canvas.create_arc(bbox, start=-90, extent=extent, outline=color, width=4, style="arc")

        if status == "printing":
            text = f"{progress}%"
            font_size = int(26 * scale)
        elif status in ("done", "finished"):
            text = "✓"
            font_size = int(34 * scale)
        elif status == "error":
            text = "⚠"
            font_size = int(30 * scale)
        elif status == "paused":
            text = "⏸"
            font_size = int(26 * scale)
        else:
            text = "🐼"
            font_size = int(30 * scale)

        text_color = color if status != "idle" else "#cdd6f4"
        self.canvas.create_text(center_x, center_y - 5, text=text, font=("Segoe UI Emoji", font_size), fill=text_color)

        # Connection indicator
        if self._mock:
            self.canvas.create_text(size - 20 - margin, margin + 5, text="DEMO", font=("Segoe UI", int(7 * scale), "bold"), fill="#ffd93d")
        elif self.mqtt_manager and self.mqtt_manager.connected_count > 0:
            self.canvas.create_oval(size - 20 - margin - 5, margin, size - 20 - margin + 5, margin + 10, fill="#6bcb77", outline="")
        else:
            self.canvas.create_oval(size - 20 - margin - 5, margin, size - 20 - margin + 5, margin + 10, fill="#f38ba8", outline="")

        self._actualizar_info_label(states, scale)

    def _actualizar_info_label(self, states: Dict, scale: float):
        if not states:
            self.info_label.configure(text="Sin datos")
            return
        
        priority = {"printing": 0, "paused": 1, "finished": 2, "preparing": 3, "idle": 4, "error": 5}
        best_state = None
        best_priority = 999
        
        for serial, state in states.items():
            st = state.get("status", "idle")
            p = priority.get(st, 99)
            if p < best_priority:
                best_priority = p
                best_state = state
        
        if best_state:
            name = best_state.get("name", "")
            status = best_state.get("status", "idle")
            progress = best_state.get("progress", 0)
            
            if status == "printing":
                info = f"{name[:12]}: {progress}%"
            elif status == "paused":
                info = f"{name[:12]}: Pausado"
            elif status in ("done", "finished"):
                info = f"{name[:12]}: Listo ✓"
            elif status == "error":
                info = f"{name[:12]}: Error"
            else:
                info = f"{name[:12]}: En espera"
            
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

    # Drag & Drop
    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x_root
        self._drag_data["y"] = event.y_root
        self._drag_data["dragging"] = False

    def _on_drag_motion(self, event):
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

    # Menu contextual
    def _mostrar_menu_contextual(self, event=None):
        menu = ctk.CTkToplevel(self)
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.attributes("-alpha", 0.95)

        frame = ctk.CTkFrame(menu, fg_color="#1e1e2e", corner_radius=10, border_width=1, border_color="#45475a")
        frame.pack(padx=2, pady=2)

        opciones = [
            ("⚙️  Configuración", self._abrir_settings),
            ("🔄  Reconectar", self._reconectar),
            ("📋  Info impresora", self._mostrar_info_impresora),
            ("─────────────", None),
            ("❌  Salir", self._salir),
        ]

        for texto, comando in opciones:
            if comando is None:
                sep = ctk.CTkFrame(frame, height=1, fg_color="#45475a")
                sep.pack(fill="x", padx=10, pady=3)
            else:
                btn = ctk.CTkButton(
                    frame, text=texto, command=lambda c=comando, m=menu: (m.destroy(), c()),
                    fg_color="transparent", hover_color="#313244",
                    text_color="#cdd6f4", anchor="w", height=32, width=200,
                    font=ctk.CTkFont(size=12)
                )
                btn.pack(fill="x", padx=5, pady=1)

        if event:
            x = event.x_root
            y = event.y_root
        else:
            x = self.btn_settings.winfo_rootx()
            y = self.btn_settings.winfo_rooty() + 30

        menu.geometry(f"+{x}+{y}")
        menu.bind("<FocusOut>", lambda e: menu.destroy())
        menu.after(100, lambda: menu.focus_set())

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

    def _mostrar_info_impresora(self):
        info_win = ctk.CTkToplevel(self)
        info_win.title("Info Impresora")
        info_win.geometry("300x250")
        info_win.resizable(False, False)
        info_win.transient(self)
        info_win.attributes("-topmost", True)

        main = ctk.CTkFrame(info_win, fg_color="#1e1e2e")
        main.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(main, text="🖨️  Estado de Impresora", font=ctk.CTkFont(size=16, weight="bold"), text_color="#00e5ff").pack(pady=(5, 10))

        states = self._get_enriched_states()
        if not states:
            ctk.CTkLabel(main, text="Sin datos de impresora", font=ctk.CTkFont(size=12), text_color="#a0a0a0").pack(expand=True)
        else:
            for serial, state in states.items():
                info_text = f"Nombre: {state.get('name', '?')}\nEstado: {state.get('status', '?')}\nProgreso: {state.get('progress', 0)}%"
                ctk.CTkLabel(main, text=info_text, font=ctk.CTkFont(size=11), text_color="#cdd6f4", justify="left").pack(anchor="w", padx=10, pady=5)

        ctk.CTkButton(main, text="Cerrar", command=info_win.destroy, fg_color="#00e5ff", hover_color="#00b8d4", text_color="#000000", height=32).pack(side="bottom", fill="x", pady=(10, 0))

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
        
        def _connect_mqtt():
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
        
        threading.Thread(target=_connect_mqtt, daemon=True).start()


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, config: dict, on_save=None):
        super().__init__(parent)
        self.config_data = config
        self.on_save = on_save
        self.parent = parent

        self.title("bambuPet - Configuración")
        self.geometry("360x420")
        self.resizable(False, False)
        self.transient(parent)

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 180
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 210
        self.geometry(f"+{x}+{y}")

        main = ctk.CTkFrame(self, fg_color="#1e1e2e")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(main, text="🐼  bambuPet", font=ctk.CTkFont(size=20, weight="bold"), text_color="#00e5ff").pack(pady=(10, 5))
        ctk.CTkLabel(main, text="Configuración del widget", font=ctk.CTkFont(size=11), text_color="#a0a0a0").pack(pady=(0, 15))

        # Scale
        scale_frame = ctk.CTkFrame(main, fg_color="transparent")
        scale_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(scale_frame, text="📐 Tamaño", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.scale_label = ctk.CTkLabel(scale_frame, text=f"{int(config['display']['scale'] * 100)}%", font=ctk.CTkFont(size=11), text_color="#00e5ff")
        self.scale_label.pack(side="right")
        self.scale_var = ctk.DoubleVar(value=config["display"]["scale"])
        ctk.CTkSlider(main, from_=0.5, to=2.0, variable=self.scale_var, command=self._on_scale_change, button_color="#00e5ff", progress_color="#00e5ff").pack(fill="x", padx=10)

        # Opacity
        opacity_frame = ctk.CTkFrame(main, fg_color="transparent")
        opacity_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(opacity_frame, text="👁️ Opacidad", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.opacity_label = ctk.CTkLabel(opacity_frame, text=f"{int(config['display']['opacity'] * 100)}%", font=ctk.CTkFont(size=11), text_color="#00e5ff")
        self.opacity_label.pack(side="right")
        self.opacity_var = ctk.DoubleVar(value=config["display"]["opacity"])
        ctk.CTkSlider(main, from_=0.2, to=1.0, variable=self.opacity_var, command=self._on_opacity_change, button_color="#00e5ff", progress_color="#00e5ff").pack(fill="x", padx=10)

        # Always on top
        self.top_var = ctk.BooleanVar(value=config["display"]["always_on_top"])
        ctk.CTkCheckBox(main, text="Siempre encima", variable=self.top_var, checkbox_height=20, fg_color="#00e5ff", hover_color="#00b8d4").pack(anchor="w", padx=10, pady=(10, 5))

        # Printers info
        ctk.CTkLabel(main, text="🖨️ Impresoras:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        for p in config.get("mqtt", {}).get("printers", []):
            ctk.CTkLabel(main, text=f"  • {p.get('name', '?')} @ {p.get('ip', '?')}", font=ctk.CTkFont(size=10), text_color="#a0a0a0").pack(anchor="w", padx=20)

        # Buttons
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkButton(btn_frame, text="💾 Guardar", command=self._guardar, fg_color="#00e5ff", hover_color="#00b8d4", text_color="#000000", font=ctk.CTkFont(size=12, weight="bold"), height=34, corner_radius=8).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="Cancelar", command=self.destroy, fg_color="#f38ba8", hover_color="#e06c75", text_color="#000000", font=ctk.CTkFont(size=12), height=34, corner_radius=8).pack(side="right", expand=True, fill="x", padx=(5, 0))

    def _on_scale_change(self, value):
        self.scale_label.configure(text=f"{int(value * 100)}%")
        self.config_data["display"]["scale"] = value
        self.parent.config_data["display"]["scale"] = value
        self.parent._configurar_ventana()
        self.parent._crear_interfaz()

    def _on_opacity_change(self, value):
        self.opacity_label.configure(text=f"{int(value * 100)}%")
        self.parent.attributes("-alpha", value)

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
