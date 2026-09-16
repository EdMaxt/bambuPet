"""
bambuPet — Panel de configuración (Tkinter)
Ventana de ajustes para el pet: tamaño, opacidad, posición y always-on-top.
"""

import json
import os
import tkinter as tk
from tkinter import ttk

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


class SettingsPanel:
    """Ventana de configuración modal para bambuPet.
    
    Se muestra como Toplevel sobre la ventana principal (parent).
    Permite ajustar scale, opacity, offset_x, offset_y y always_on_top.
    Los cambios se guardan en config.json al presionar Guardar.
    """
    
    # Estilo visual
    BG_COLOR = "#1a1a2e"
    FG_COLOR = "#e0e0e0"
    ENTRY_BG = "#16213e"
    ENTRY_FG = "#e0e0e0"
    BUTTON_BG = "#0f3460"
    BUTTON_FG = "#e0e0e0"
    ACCENT_COLOR = "#e94560"
    SCALE_TROUGH = "#16213e"
    SCALE_BG = "#0f3460"
    FONT_FAMILY = "Segoe UI"
    
    def __init__(self, parent, config, on_save_callback):
        """Inicializar el panel de configuración.
        
        Args:
            parent: Ventana principal (Tk/Toplevel) sobre la que se muestra.
            config: Diccionario de configuración actual.
            on_save_callback: Función a llamar después de guardar (ej. para recargar UI).
        """
        self.parent = parent
        self.config = config
        self.on_save_callback = on_save_callback
        
        # Extraer valores actuales de display
        self.display_config = config.get("display", {})
        self.scale_value = float(self.display_config.get("scale", 1.0))
        self.opacity_value = float(self.display_config.get("opacity", 0.95))
        self.offset_x_value = int(self.display_config.get("offset_x", 20))
        self.offset_y_value = int(self.display_config.get("offset_y", 20))
        self.always_on_top_value = bool(self.display_config.get("always_on_top", True))
        
        # Variable de guardado exitoso
        self._saved = False
        
        self._crear_ventana()
        self._crear_widgets()
    
    def _crear_ventana(self):
        """Crear la ventana Toplevel con estilo transparente."""
        self.window = tk.Toplevel(self.parent)
        self.window.title("⚙️ Configuración bambuPet")
        self.window.geometry("320x340")
        self.window.resizable(False, False)
        self.window.configure(bg=self.BG_COLOR)
        
        # Hacer la ventana semi-transparente
        self.window.attributes("-alpha", 0.95)
        
        # Centrar sobre el padre
        self.window.transient(self.parent)
        self.window.grab_set()
        
        # Cerrar con Escape
        self.window.bind("<Escape>", lambda e: self._cerrar())
    
    def _crear_widgets(self):
        """Crear todos los widgets del panel."""
        # Frame principal con padding
        main_frame = tk.Frame(self.window, bg=self.BG_COLOR, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Título ---
        titulo = tk.Label(
            main_frame,
            text="Configuración del Pet",
            font=(self.FONT_FAMILY, 14, "bold"),
            bg=self.BG_COLOR,
            fg=self.ACCENT_COLOR
        )
        titulo.pack(pady=(0, 15))
        
        # --- Tamaño (Scale) ---
        self._crear_escala(
            parent=main_frame,
            label="Tamaño",
            value=self.scale_value,
            from_=0.5,
            to=2.0,
            resolution=0.05,
            unit="%",
            callback=self._on_scale_change
        )
        
        # --- Opacidad (Scale) ---
        self._crear_escala(
            parent=main_frame,
            label="Opacidad",
            value=self.opacity_value,
            from_=0.2,
            to=1.0,
            resolution=0.05,
            unit="%",
            callback=self._on_opacity_change
        )
        
        # --- Offset X ---
        offset_frame = tk.Frame(main_frame, bg=self.BG_COLOR)
        offset_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            offset_frame,
            text="Offset X / Y",
            font=(self.FONT_FAMILY, 10),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR,
            width=12,
            anchor="w"
        ).pack(side=tk.LEFT)
        
        self.offset_x_entry = tk.Entry(
            offset_frame,
            font=(self.FONT_FAMILY, 10),
            bg=self.ENTRY_BG,
            fg=self.ENTRY_FG,
            insertbackground=self.ENTRY_FG,
            width=6,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightcolor=self.ACCENT_COLOR,
            highlightbackground=self.BUTTON_BG
        )
        self.offset_x_entry.insert(0, str(self.offset_x_value))
        self.offset_x_entry.pack(side=tk.LEFT, padx=(5, 5))
        
        self.offset_y_entry = tk.Entry(
            offset_frame,
            font=(self.FONT_FAMILY, 10),
            bg=self.ENTRY_BG,
            fg=self.ENTRY_FG,
            insertbackground=self.ENTRY_FG,
            width=6,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightcolor=self.ACCENT_COLOR,
            highlightbackground=self.BUTTON_BG
        )
        self.offset_y_entry.insert(0, str(self.offset_y_value))
        self.offset_y_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        # --- Always on Top (Checkbutton) ---
        check_frame = tk.Frame(main_frame, bg=self.BG_COLOR)
        check_frame.pack(fill=tk.X, pady=8)
        
        self.on_top_var = tk.BooleanVar(value=self.always_on_top_value)
        
        self.on_top_check = tk.Checkbutton(
            check_frame,
            text="Siempre visible (Always on Top)",
            variable=self.on_top_var,
            font=(self.FONT_FAMILY, 10),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR,
            activebackground=self.BG_COLOR,
            activeforeground=self.FG_COLOR,
            selectcolor=self.BG_COLOR,
            highlightthickness=0,
            bd=0,
            command=self._on_top_change
        )
        self.on_top_check.pack(anchor="w")
        
        # --- Botones ---
        button_frame = tk.Frame(main_frame, bg=self.BG_COLOR)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))
        
        # Botón Guardar
        self.btn_guardar = tk.Button(
            button_frame,
            text="Guardar",
            font=(self.FONT_FAMILY, 10, "bold"),
            bg=self.ACCENT_COLOR,
            fg="white",
            activebackground="#c0392b",
            activeforeground="white",
            relief=tk.FLAT,
            padx=15,
            pady=5,
            cursor="hand2",
            command=self._guardar
        )
        self.btn_guardar.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Botón Cancelar
        self.btn_cancelar = tk.Button(
            button_frame,
            text="Cancelar",
            font=(self.FONT_FAMILY, 10),
            bg=self.BUTTON_BG,
            fg=self.BUTTON_FG,
            activebackground="#1a5276",
            activeforeground=self.BUTTON_FG,
            relief=tk.FLAT,
            padx=15,
            pady=5,
            cursor="hand2",
            command=self._cerrar
        )
        self.btn_cancelar.pack(side=tk.RIGHT)
    
    def _crear_escala(self, parent, label, value, from_, to, resolution, unit, callback):
        """Crear un Label + Scale con formato consistente.
        
        Args:
            parent: Frame contenedor.
            label: Texto descriptivo.
            value: Valor inicial.
            from_: Mínimo del Scale.
            to: Máximo del Scale.
            resolution: Incremento del Scale.
            unit: Unidad de medida (mostrada como "%").
            callback: Función llamada al cambiar el valor.
        """
        frame = tk.Frame(parent, bg=self.BG_COLOR)
        frame.pack(fill=tk.X, pady=3)
        
        # Fila superior: label + valor
        top_frame = tk.Frame(frame, bg=self.BG_COLOR)
        top_frame.pack(fill=tk.X)
        
        tk.Label(
            top_frame,
            text=label,
            font=(self.FONT_FAMILY, 10),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR,
            width=12,
            anchor="w"
        ).pack(side=tk.LEFT)
        
        # Variable y label de valor
        var = tk.DoubleVar(value=value)
        valor_label = tk.Label(
            top_frame,
            text=f"{int(value * 100)}{unit}",
            font=(self.FONT_FAMILY, 10, "bold"),
            bg=self.BG_COLOR,
            fg=self.ACCENT_COLOR
        )
        valor_label.pack(side=tk.RIGHT)
        
        # Scale
        scale = tk.Scale(
            frame,
            from_=from_,
            to=to,
            resolution=resolution,
            orient=tk.HORIZONTAL,
            variable=var,
            font=(self.FONT_FAMILY, 8),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR,
            troughcolor=self.SCALE_TROUGH,
            activebackground=self.ACCENT_COLOR,
            sliderrelief=tk.FLAT,
            highlightthickness=0,
            bd=0,
            showvalue=False,
            command=lambda v: [
                callback(float(v)),
                valor_label.config(text=f"{int(float(v) * 100)}{unit}")
            ]
        )
        scale.pack(fill=tk.X)
        
        # Referencias para acceso posterior
        setattr(self, f"_{label.lower().replace(' ', '_')}_scale", scale)
        setattr(self, f"_{label.lower().replace(' ', '_')}_var", var)
    
    # === Callbacks de cambios ===
    
    def _on_scale_change(self, value):
        """Callback al mover el slider de tamaño."""
        self.scale_value = value
    
    def _on_opacity_change(self, value):
        """Callback al mover el slider de opacidad."""
        self.opacity_value = value
    
    def _on_top_change(self):
        """Callback al cambiar Always on Top."""
        self.always_on_top_value = self.on_top_var.get()
    
    def _leer_offsets(self):
        """Leer y validar los valores de offset de los Entry."""
        try:
            x = int(self.offset_x_entry.get())
        except (ValueError, TypeError):
            x = self.offset_x_value
        
        try:
            y = int(self.offset_y_entry.get())
        except (ValueError, TypeError):
            y = self.offset_y_value
        
        # Limitar a rangos razonables
        x = max(-500, min(500, x))
        y = max(-500, min(500, y))
        
        return x, y
    
    def _guardar(self):
        """Guardar configuración en config.json y cerrar."""
        # Leer offsets validados
        x, y = self._leer_offsets()
        self.offset_x_value = x
        self.offset_y_value = y
        
        # Actualizar config en memoria
        self.config["display"]["scale"] = round(self.scale_value, 2)
        self.config["display"]["opacity"] = round(self.opacity_value, 2)
        self.config["display"]["offset_x"] = x
        self.config["display"]["offset_y"] = y
        self.config["display"]["always_on_top"] = self.always_on_top_value
        
        # Guardar en archivo
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando config: {e}")
        
        self._saved = True
        
        # Llamar callback si existe
        if self.on_save_callback:
            self.on_save_callback()
        
        self._cerrar()
    
    def _cerrar(self):
        """Cerrar la ventana sin guardar."""
        self.window.grab_release()
        self.window.destroy()
    
    def show(self):
        """Mostrar la ventana y esperar hasta que se cierre."""
        self.window.wait_window()
        return self._saved


# === Función de conveniencia ===
def open_settings(parent, config, on_save_callback=None):
    """Abrir el panel de configuración.
    
    Args:
        parent: Ventana padre (Tk).
        config: Diccionario de configuración.
        on_save_callback: Función a llamar al guardar.
    
    Returns:
        bool: True si se guardaron cambios, False si se canceló.
    """
    panel = SettingsPanel(parent, config, on_save_callback)
    return panel.show()


if __name__ == "__main__":
    # Prueba independiente
    root = tk.Tk()
    root.title("bambuPet — Prueba Settings")
    root.geometry("400x300")
    root.configure(bg="#010101")
    
    # Simular config
    test_config = {
        "mqtt": {"poll_interval_sec": 10, "reconnect_delay_sec": 5, "printers": []},
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
    
    def on_saved():
        print("Configuración guardada correctamente")
    
    btn = tk.Button(
        root,
        text="Abrir Configuración",
        font=("Segoe UI", 12),
        bg="#e94560",
        fg="white",
        command=lambda: open_settings(root, test_config, on_saved)
    )
    btn.pack(expand=True)
    
    root.mainloop()
