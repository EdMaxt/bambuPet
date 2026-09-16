"""
bambuPet Mock - Simulador de mensajes MQTT para pruebas de UI
"""

import json
import threading
import time
import logging
from typing import Dict, Callable, Optional

logger = logging.getLogger(__name__)


class MockRocky:
    """Simula mensajes MQTT de una impresora BambuLab Rocky."""
    
    def __init__(self, on_message: Callable[[str, dict], None], serial: str = "0309CA510501451"):
        self.on_message = on_message
        self.serial = serial
        self.running = False
        self._thread = None
        self.progress = 0
        self.status = "idle"
        
    def start(self):
        """Inicia el simulador en un hilo."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("🎭 Modo DEMO activado — Simulando Rocky")
        
    def stop(self):
        """Detiene el simulador."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
            
    def _run(self):
        """Bucle principal de simulación."""
        # Mensajes iniciales
        self._send_full_status()
        
        # Simular inicio de impresión después de 3s
        time.sleep(3)
        self.status = "printing"
        self.progress = 0
        
        # Simular progreso
        stages = [
            ("preparing", 0, 2),
            ("printing", 0, 10),
            ("printing", 10, 50),
            ("printing", 50, 90),
            ("printing", 90, 100),
            ("done", 100, 5),
        ]
        
        for status, start_prog, end_prog in stages:
            if not self.running:
                break
            self.status = status
            self.progress = start_prog
            
            # Enviar mensajes parciales durante esta fase
            duration = 5 if status == "printing" else 3
            steps = 5
            for i in range(steps):
                if not self.running:
                    break
                partial = start_prog + (end_prog - start_prog) * (i + 1) // steps
                self.progress = partial
                self._send_push_status()
                time.sleep(duration / steps)
                
        # Reiniciar ciclo
        time.sleep(5)
        if self.running:
            self._run()  # Reiniciar simulación
            
    def _send_full_status(self):
        """Envía estado completo (pushall)."""
        data = {
            "print": {
                "mc_percent": self.progress,
                "mc_remaining_time": 42,
                "mc_print_stage": "2" if self.status == "printing" else "1",
                "gcode_state": "RUNNING" if self.status == "printing" else "IDLE",
                "gcode_file": "Carnet_de_Notes_de_Poche.gcode.3mf",
                "subtask_name": "Carnet_de_Notes_de_Poche",
                "nozzle_temper": 180.5 if self.status == "printing" else 28.0,
                "nozzle_target_temper": 180 if self.status == "printing" else 0,
                "bed_temper": 50.2 if self.status == "printing" else 28.0,
                "bed_target_temper": 65 if self.status == "printing" else 0,
                "wifi_signal": "-56dBm",
                "ams_status": 768,
                "hw_switch_state": 1,
                "spd_mag": 100,
                "spd_lvl": 2,
                "print_error": 0,
                "wifi_signal": f"{-50 - (self.progress % 7)}dBm",
                "layer_num": 0,
                "total_layer_num": 24,
            },
            "temperature": {
                "temp": [180, 180.5] if self.status == "printing" else [0, 28],
                "bed_temp": [65, 50.2] if self.status == "printing" else [0, 28]
            },
            "lights_report": [{"node": "chamber_light", "mode": "on" if self.status == "printing" else "off"}],
            "ams": {
                "ams": [{
                    "id": "0",
                    "tray": [
                        {"id": "0", "state": 3, "remain": 100, "tray_info_idx": "GFSNL03", "tray_type": "PLA", "tray_color": "000000FF"},
                        {"id": "2", "state": 3, "remain": 100, "tray_info_idx": "GFSNL03", "tray_type": "PLA", "tray_color": "A03CF7FF"},
                        {"id": "3", "state": 3, "remain": 100, "tray_info_idx": "GFSNL03", "tray_type": "PLA", "tray_color": "FFFFFFFF"}
                    ]
                }],
            },
            "command": "push_status",
            "msg": 0,
            "sequence_id": str(int(time.time() * 1000))
        }
        self.on_message(self.serial, data)
        
    def _send_push_status(self):
        """Envía mensaje parcial (push_status)."""
        data = {
            "print": {
                "mc_percent": self.progress,
                "mc_remaining_time": max(0, 42 - self.progress // 2),
                "nozzle_temper": 180.0 + (self.progress % 10) * 0.1 if self.status == "printing" else 28.0,
                "bed_temper": 50.0 + (self.progress % 5) * 0.2 if self.status == "printing" else 28.0,
                "wifi_signal": "-56dBm",
                "gcode_state": "RUNNING" if self.status == "printing" else "IDLE",
                "layer_num": int(self.progress * 24 / 100),
                "total_layer_num": 24,
                "wifi_signal": f"{-50 - (self.progress % 7)}dBm",
            },
            "temperature": {
                "temp": [180, 180.0 + (self.progress % 10) * 0.1] if self.status == "printing" else [0, 28],
                "bed_temp": [65, 50.0 + (self.progress % 5) * 0.2] if self.status == "printing" else [0, 28]
            },
            "lights_report": [{"node": "chamber_light", "mode": "on" if self.status == "printing" else "off"}],
            "command": "push_status",
            "msg": 0,
            "sequence_id": str(int(time.time() * 1000))
        }
        self.on_message(self.serial, data)
