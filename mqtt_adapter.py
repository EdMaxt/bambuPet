"""
bambuPet — Adaptador MQTT para UI Tkinter
Conecta mqtt_manager.py con callbacks de la interfaz gráfica.
"""

import json
import logging
import threading
import os
from typing import Callable, Dict, Optional, Any

from mqtt_manager import MQTTManager
from parser import parse_printer_status, PrinterStateTracker

logger = logging.getLogger(__name__)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class PetMqttAdapter:
    """
    Adaptador entre MQTTManager y la UI Tkinter.
    
    - Carga configuración desde config.json
    - Crea y gestiona instancias de LocalMQTTClient por impresora
    - Parsea mensajes crudos y emite diccionarios simplificados a la UI
    - Seguro para uso desde múltiples hilos (thread-safe)
    """

    # Ruta al archivo de configuración por defecto
    DEFAULT_CONFIG_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.json"
    )

    def __init__(
        self,
        on_state_change_callback: Callable[[Dict[str, Any]], None],
        config_path: Optional[str] = None,
    ):
        """
        Inicializa el adaptador.

        Args:
            on_state_change_callback: Función a llamar cuando cambie el estado
                                      de una impresora. Recibe un dict simplificado.
            config_path: Ruta opcional a config.json. Usa la ruta por defecto si no se especifica.
        """
        self._ui_callback = on_state_change_callback
        self._config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._manager: Optional[MQTTManager] = None
        self._config: Dict = {}
        self._trackers: Dict[str, PrinterStateTracker] = {}
        self._printer_names: Dict[str, str] = {}  # serial -> name
        self._connected: Dict[str, bool] = {}      # serial -> bool
        self._latest_states: Dict[str, Dict] = {}  # serial -> estado simplificado
        self._started = False
        self.lock = threading.Lock()

        logger.info("PetMqttAdapter inicializado")

    # ───────────────────────── Públicos ─────────────────────────

    def start(self) -> bool:
        """
        Carga config, crea MQTTManager y conecta a todas las impresoras.

        Returns:
            True si se inició correctamente, False si hubo error.
        """
        try:
            with self.lock:
                if self._started:
                    logger.warning("El adaptador ya está iniciado")
                    return True

                if not self._cargar_config():
                    return False

                self._crear_trackers()
                self._manager = MQTTManager(on_state_change=self._handle_message)
                self._agregar_impresoras()
                self._manager.start_all()
                self._started = True
                logger.info("✅ Adaptador MQTT iniciado correctamente")
                return True

        except Exception as e:
            logger.error(f"Error al iniciar adaptador: {e}")
            return False

    def stop(self) -> None:
        """Desconecta todas las impresoras y libera recursos."""
        try:
            with self.lock:
                if self._manager:
                    self._manager.stop_all()
                    self._manager = None
                self._connected.clear()
                self._started = False
                logger.info("⏹ Adaptador MQTT detenido")
        except Exception as e:
            logger.error(f"Error al detener adaptador: {e}")

    def request_status(self) -> None:
        """
        Solicita pushall (estado completo) a todas las impresoras conectadas.
        """
        try:
            with self.lock:
                if self._manager and self._started:
                    self._manager.request_all_status()
                    logger.debug("Pushall solicitado a todas las impresoras")
        except Exception as e:
            logger.error(f"Error al solicitar estado: {e}")

    def get_latest_state(self, serial: Optional[str] = None) -> Optional[Dict]:
        """
        Retorna el último estado conocido de una impresora.

        Args:
            serial: Número de serie. Si es None, retorna la primera disponible.

        Returns:
            Diccionario simplificado de estado o None.
        """
        try:
            with self.lock:
                if serial:
                    return self._latest_states.get(serial)

                # Sin serial: retornar la última impresora que tenga estado
                if self._latest_states:
                    return next(iter(self._latest_states.values()))
                return None
        except Exception as e:
            logger.error(f"Error al obtener estado: {e}")
            return None

    def get_all_states(self) -> Dict[str, Dict]:
        """
        Retorna los estados de todas las impresoras.

        Returns:
            Dict con serial -> estado simplificado.
        """
        try:
            with self.lock:
                return self._latest_states.copy()
        except Exception as e:
            logger.error(f"Error al obtener todos los estados: {e}")
            return {}

    @property
    def is_running(self) -> bool:
        """Indica si el adaptador está activo."""
        return self._started

    # ───────────────────────── Internos ─────────────────────────

    def _cargar_config(self) -> bool:
        """
        Carga el archivo config.json.

        Returns:
            True si se cargó correctamente.
        """
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)

            printers = self._config.get("mqtt", {}).get("printers", [])
            if not printers:
                logger.warning("No hay impresoras configuradas en config.json")
                return False

            logger.info(f"Config cargada: {len(printers)} impresora(s)")
            return True

        except FileNotFoundError:
            logger.error(f"Archivo de configuración no encontrado: {self._config_path}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando config.json: {e}")
            return False
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            return False

    def _crear_trackers(self) -> None:
        """Crea trackers de estado para cada impresora configurada."""
        printers = self._config.get("mqtt", {}).get("printers", [])
        for p in printers:
            serial = p["serial"]
            name = p.get("name", serial)
            self._trackers[serial] = PrinterStateTracker(name=name)
            self._printer_names[serial] = name
            self._connected[serial] = False
            logger.info(f"Tracker creado: {name} ({serial})")

    def _agregar_impresoras(self) -> None:
        """Agrega todas las impresoras configuradas al manager."""
        if not self._manager:
            return
        printers = self._config.get("mqtt", {}).get("printers", [])
        for p in printers:
            try:
                self._manager.add_printer(p)
            except Exception as e:
                logger.error(f"Error agregando impresora {p.get('serial', '?')}: {e}")

    def _handle_message(self, serial: str, raw_data: Dict) -> None:
        """
        Callback interno llamado por MQTTManager al recibir un mensaje.

        Args:
            serial: Número de serie de la impresora.
            raw_data: Datos crudos del mensaje MQTT.
        """
        try:
            with self.lock:
                # Obtener tracker o crear uno fallback
                tracker = self._trackers.get(serial)
                if not tracker:
                    logger.warning(f"Sin tracker para {serial}, creando fallback")
                    name = self._printer_names.get(serial, serial)
                    tracker = PrinterStateTracker(name=name)
                    self._trackers[serial] = tracker

                # Parsear y preservar estado entre mensajes parciales
                parsed = tracker.update(raw_data)

                # Construir diccionario simplificado para la UI
                state = self._construir_estado_ui(serial, parsed)
                self._latest_states[serial] = state

            # Llamar callback de UI fuera del lock para no bloquear
            if self._ui_callback:
                try:
                    self._ui_callback(state)
                except Exception as e:
                    logger.error(f"Error en callback de UI: {e}")

        except Exception as e:
            logger.error(f"Error procesando mensaje de {serial}: {e}")

    def _construir_estado_ui(self, serial: str, parsed: Dict) -> Dict[str, Any]:
        """
        Construye el diccionario simplificado que espera la UI Tkinter.

        Args:
            serial: Número de serie.
            parsed: Estado parseado por PrinterStateTracker.

        Returns:
            Diccionario con el formato esperado por la UI.
        """
        raw_data = parsed.get("_raw_data", {})
        temp_data = raw_data.get("temperature", {})

        # Extraer temperaturas completas (target + current)
        nozzle_temp = self._extraer_nozzle_completa(temp_data)
        bed_temp = self._extraer_bed_completa(temp_data)

        name = self._printer_names.get(serial, parsed.get("name", serial))

        return {
            "name": name,
            "progress": parsed.get("progress", 0),
            "status": parsed.get("status", "unknown"),
            "nozzle_temp": nozzle_temp,
            "bed_temp": bed_temp,
            "current_file": parsed.get("current_file", ""),
            "time_remaining": parsed.get("time_remaining", 0),
            "connected": self._connected.get(serial, False),
        }

    @staticmethod
    def _extraer_nozzle_completa(temp_data: Dict) -> Dict[str, float]:
        """
        Extrae temperatura del nozzle con target y current.

        Args:
            temp_data: Diccionario de temperaturas del mensaje MQTT.

        Returns:
            Dict con keys "target" y "current".
        """
        result = {"target": 0.0, "current": 0.0}

        # Formato lista: temp = [target, current]
        if "temp" in temp_data and isinstance(temp_data["temp"], list):
            if len(temp_data["temp"]) >= 2:
                try:
                    result["target"] = float(temp_data["temp"][0])
                    result["current"] = float(temp_data["temp"][1])
                    return result
                except (ValueError, TypeError):
                    pass

        # Formato nozzle_temper directo (solo current)
        if "nozzle_temper" in temp_data:
            try:
                result["current"] = float(temp_data["nozzle_temper"])
            except (ValueError, TypeError):
                pass

        return result

    @staticmethod
    def _extraer_bed_completa(temp_data: Dict) -> Dict[str, float]:
        """
        Extrae temperatura de la cama con target y current.

        Args:
            temp_data: Diccionario de temperaturas del mensaje MQTT.

        Returns:
            Dict con keys "target" y "current".
        """
        result = {"target": 0.0, "current": 0.0}

        # Formato lista: bed_temp = [target, current]
        if isinstance(temp_data.get("bed_temp"), list):
            if len(temp_data["bed_temp"]) >= 2:
                try:
                    result["target"] = float(temp_data["bed_temp"][0])
                    result["current"] = float(temp_data["bed_temp"][1])
                    return result
                except (ValueError, TypeError):
                    pass

        # Formato bed_tener directo
        if "bed_temper" in temp_data:
            try:
                result["current"] = float(temp_data["bed_temper"])
            except (ValueError, TypeError):
                pass

        # Formato bed_temp directo (valor único)
        elif "bed_temp" in temp_data and not isinstance(temp_data["bed_temp"], list):
            try:
                result["current"] = float(temp_data["bed_temp"])
            except (ValueError, TypeError):
                pass

        return result

    def _on_connect(self, serial: str) -> None:
        """Callback cuando una impresora se conecta."""
        with self.lock:
            self._connected[serial] = True
            # Actualizar último estado existente o crear uno mínimo
            if serial in self._latest_states:
                self._latest_states[serial]["connected"] = True
            else:
                self._latest_states[serial] = {
                    "name": self._printer_names.get(serial, serial),
                    "progress": 0,
                    "status": "connecting",
                    "nozzle_temp": {"target": 0, "current": 0},
                    "bed_temp": {"target": 0, "current": 0},
                    "current_file": "",
                    "time_remaining": 0,
                    "connected": True,
                }
        logger.info(f"🟢 {serial} conectado")

    def _on_disconnect(self, serial: str) -> None:
        """Callback cuando una impresora se desconecta."""
        with self.lock:
            self._connected[serial] = False
            if serial in self._latest_states:
                self._latest_states[serial]["connected"] = False
                self._latest_states[serial]["status"] = "disconnected"
        logger.warning(f"🔴 {serial} desconectado")

    # Alias en español para mantener la API del manager
    _handle_connect = _on_connect
    _handle_disconnect = _on_disconnect
