"""
bambuPet — Parser de mensajes MQTT BambuLab
"""

from typing import Dict, Any, Optional
from datetime import datetime


class PrinterStateTracker:
    """
    Rastrea el estado de una impresora, manteniendo valores conocidos
    entre mensajes parciales (push_status no incluye mc_percent).
    """
    
    def __init__(self, name: str = ""):
        self.name = name
        self.last_known = {}
    
    def update(self, raw_data: dict) -> dict:
        """
        Actualiza el estado con nuevos datos, preservando valores anteriores
        si los nuevos son N/A o faltan.
        """
        print_data = raw_data.get("print", {})
        
        # Si el mensaje trae mc_percent, actualizar
        if "mc_percent" in print_data:
            self.last_known["mc_percent"] = print_data["mc_percent"]
        
        # Si el mensaje trae mc_print_stage, actualizar
        if "mc_print_stage" in print_data:
            self.last_known["mc_print_stage"] = print_data["mc_print_stage"]
        
        # Si el mensaje trae gcode_state, actualizar
        if "gcode_state" in print_data:
            self.last_known["gcode_state"] = print_data["gcode_state"]
        
        # Si el mensaje trae current_file, actualizar
        if "gcode_file" in print_data:
            self.last_known["gcode_file"] = print_data["gcode_file"]
        
        return self.get_enriched_state(raw_data)
    
    def get_enriched_state(self, raw_data: dict) -> dict:
        """Retorna el estado enriquecido con valores conocidos."""
        parsed = parse_printer_status(raw_data)
        
        # Usar último valor conocido si el parse dio 0/N/A
        if parsed.get("progress", 0) == 0 and "mc_percent" in self.last_known:
            parsed["progress"] = self.last_known["mc_percent"]
        
        parsed["name"] = self.name
        return parsed


def parse_printer_status(raw_data: Dict) -> Dict[str, Any]:
    """
    Parsea un mensaje MQTT crudo de impresora BambuLab y extrae
    los campos relevantes para bambuPet.
    """
    
    print_data = raw_data.get("print", {})
    temp_data = raw_data.get("temperature", {})
    lights_data = raw_data.get("lights_report", [{}])[0] if raw_data.get("lights_report") else {}
    
    # Progreso
    progress = print_data.get("mc_percent", 0)
    time_remaining = print_data.get("mc_remaining_time", 0)
    
    # Estado
    stage = print_data.get("stage", "0")
    gcode_state = print_data.get("gcode_state", "UNKNOWN")
    status = _map_status(stage, gcode_state)
    
    # Archivo actual
    current_file = print_data.get("gcode_file", print_data.get("subtask_name", ""))
    
    # Temperaturas
    nozzle_temp = _extract_nozzle_temp(temp_data)
    bed_temp = _extract_bed_temp(temp_data)
    
    # Luz
    chamber_light = lights_data.get("mode", "unknown")
    
    return {
        "progress": int(progress) if progress else 0,
        "time_remaining": int(time_remaining) if time_remaining else 0,
        "status": status,
        "stage": stage,
        "gcode_state": gcode_state,
        "current_file": current_file,
        "nozzle_temp": nozzle_temp,
        "bed_temp": bed_temp,
        "chamber_light": chamber_light,
        "raw": raw_data,  # Mantener raw para debug
        "last_update": datetime.now().isoformat()
    }


def _map_status(stage: str, gcode_state: str) -> str:
    """Mapea stage + gcode_state a un estado simplificado."""
    stage_map = {
        "0": "idle",
        "1": "preparing",
        "2": "printing",
        "3": "paused",
        "4": "error",
        "5": "done"
    }
    
    gcode_map = {
        "IDLE": "idle",
        "PREPARE": "preparing",
        "RUNNING": "printing",
        "PAUSE": "paused",
        "FINISH": "done",
        "FAILED": "error",
        "SLICING": "preparing"
    }
    
    if gcode_state == "FINISH":
        return "done"
    if gcode_state == "FAILED":
        return "error"
    if gcode_state == "PAUSE":
        return "paused"
    
    return stage_map.get(stage, "idle")


def _extract_nozzle_temp(temp_data: Dict) -> Dict[str, float]:
    """Extraer temperatura del nozzle."""
    result = {"target": 0, "current": 0}
    if "temp" in temp_data and isinstance(temp_data["temp"], list) and len(temp_data["temp"]) >= 2:
        result["target"] = float(temp_data["temp"][0])
        result["current"] = float(temp_data["temp"][1])
    return result


def _extract_bed_temp(temp_data: Dict) -> Dict[str, float]:
    """Extraer temperatura de la cama."""
    result = {"target": 0, "current": 0}
    if "bed_temp" in temp_data and isinstance(temp_data["bed_temp"], list) and len(temp_data["bed_temp"]) >= 2:
        result["target"] = float(temp_data["bed_temp"][0])
        result["current"] = float(temp_data["bed_temp"][1])
    return result


def get_print_summary(printers_states: Dict[str, Dict]) -> Dict[str, Any]:
    """Genera un resumen de todas las impresoras para la UI compacta."""
    if not printers_states:
        return {"status": "no_printers", "progress": 0, "name": ""}
    
    priority = {"printing": 0, "paused": 1, "done": 2, "preparing": 3, "idle": 4, "error": 5}
    
    best_printer = None
    best_priority = 999
    
    for serial, state in printers_states.items():
        status = state.get("status", "idle")
        p = priority.get(status, 99)
        
        if p < best_priority:
            best_priority = p
            best_printer = state
            best_printer["serial"] = serial
    
    if best_printer:
        return best_printer
    
    return {"status": "no_printers", "progress": 0, "name": ""}
