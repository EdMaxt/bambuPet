"""
bambuPet — Test Suite
Tests end-to-end para parser, mqtt_manager y main.
"""
import sys
import os
import json
import pytest

# Añadir el directorio del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser import parse_printer_status, get_print_summary, PrinterStateTracker


class TestParsePrinterStatus:
    """Tests para parse_printer_status()"""

    def test_parse_complete_printing_message(self):
        """Debe parsear correctamente un mensaje de impresión en progreso."""
        raw = {
            "print": {
                "mc_percent": 45,
                "mc_remaining_time": 120,
                "stage": "2",
                "gcode_state": "RUNNING",
                "gcode_file": "test_model.3mf"
            },
            "temperature": {
                "nozzle_temper": 210,
                "bed_temper": 60
            },
            "lights_report": [{"mode": "on"}]
        }

        result = parse_printer_status(raw)

        assert result["progress"] == 45
        assert result["time_remaining"] == 120
        assert result["status"] == "printing"
        assert result["gcode_state"] == "RUNNING"
        assert result["current_file"] == "test_model.3mf"
        assert result["nozzle_temp"] == 210
        assert result["bed_temp"] == 60
        assert result["chamber_light"] == "on"

    def test_parse_idle_message(self):
        """Debe parsear correctamente un mensaje de impresora idle."""
        raw = {
            "print": {
                "mc_percent": 0,
                "mc_remaining_time": 0,
                "stage": "0",
                "gcode_state": "IDLE"
            },
            "temperature": {
                "nozzle_temper": 25,
                "bed_temper": 25
            }
        }

        result = parse_printer_status(raw)

        assert result["progress"] == 0
        assert result["status"] == "idle"
        assert result["gcode_state"] == "IDLE"

    def test_parse_finished_message(self):
        """Debe parsear correctamente un mensaje de impresión completada."""
        raw = {
            "print": {
                "mc_percent": 100,
                "mc_remaining_time": 0,
                "stage": "12",
                "gcode_state": "FINISH"
            },
            "temperature": {
                "nozzle_temper": 210,
                "bed_temper": 60
            }
        }

        result = parse_printer_status(raw)

        assert result["progress"] == 100
        assert result["status"] == "finished"

    def test_parse_empty_message(self):
        """Debe manejar un mensaje vacío sin errores."""
        raw = {}

        result = parse_printer_status(raw)

        assert result["progress"] == 0
        assert result["status"] == "unknown"
        assert result["current_file"] == ""

    def test_parse_paused_message(self):
        """Debe parsear correctamente un mensaje de pausa."""
        raw = {
            "print": {
                "mc_percent": 30,
                "gcode_state": "PAUSE"
            }
        }

        result = parse_printer_status(raw)

        assert result["progress"] == 30
        assert result["status"] == "paused"


class TestPrinterStateTracker:
    """Tests para PrinterStateTracker"""

    def test_tracker_preserves_progress_on_partial_messages(self):
        """Debe mantener el progreso conocido cuando un mensaje no lo incluye."""
        tracker = PrinterStateTracker(name="Test")

        # Primer mensaje con progreso
        raw1 = {"print": {"mc_percent": 50, "gcode_state": "RUNNING"}}
        result1 = tracker.update(raw1)
        assert result1["progress"] == 50

        # Segundo mensaje sin progreso (push_status a veces no lo incluye)
        raw2 = {"print": {"gcode_state": "RUNNING"}}
        result2 = tracker.update(raw2)
        assert result2["progress"] == 50  # Debe mantener el valor anterior

    def test_tracker_resets_progress_on_new_print(self):
        """Debe resetear el progreso cuando inicia un nuevo print."""
        tracker = PrinterStateTracker(name="Test")

        # Primer print completado
        raw1 = {"print": {"mc_percent": 100, "gcode_state": "FINISH"}}
        tracker.update(raw1)

        # Nuevo print iniciado
        raw2 = {"print": {"mc_percent": 0, "gcode_state": "RUNNING"}}
        result2 = tracker.update(raw2)
        assert result2["progress"] == 0

    def test_tracker_includes_name(self):
        """Debe incluir el nombre de la impresora en el estado."""
        tracker = PrinterStateTracker(name="Rocky")

        raw = {"print": {"gcode_state": "IDLE"}}
        result = tracker.update(raw)

        assert result["name"] == "Rocky"


class TestGetPrintSummary:
    """Tests para get_print_summary()"""

    def test_summary_with_active_print(self):
        """Debe generar un resumen correcto con impresión activa."""
        # Estructura correcta: {serial: parsed_state}
        printers = {
            "0309CA510501451": {
                "progress": 75,
                "time_remaining": 30,
                "current_file": "benchy.3mf",
                "status": "printing",
                "name": "Rocky"
            }
        }

        result = get_print_summary(printers)

        assert "75%" in result
        assert "benchy.3mf" in result

    def test_summary_when_idle(self):
        """Debe generar un resumen correcto cuando está idle."""
        printers = {
            "0309CA510501451": {
                "progress": 0,
                "status": "idle",
                "name": "Rocky"
            }
        }

        result = get_print_summary(printers)

        assert "idle" in result.lower() or "sin" in result.lower() or "inactiv" in result.lower()

    def test_summary_with_empty_data(self):
        """Debe manejar datos vacíos sin errores."""
        raw = {}

        result = get_print_summary(raw)

        assert isinstance(result, str)
        assert len(result) > 0
