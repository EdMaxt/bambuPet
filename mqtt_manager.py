"""
bambuPet — MQTT Manager para conexión local directa a impresoras BambuLab
"""

import json
import ssl
import threading
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

logger = logging.getLogger(__name__)

# FIX: No configurar logging básico en módulo — usar handler solo si no hay otros
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class LocalMQTTClient:
    """
    Cliente MQTT directo a una impresora BambuLab en red local.
    
    Cada impresora es su propio broker MQTT (puerto 8883).
    Requiere Developer Mode activado en la impresora.
    """
    
    def __init__(
        self,
        printer_ip: str,
        serial: str,
        access_code: str,
        on_message: Optional[Callable] = None,
        on_connect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None
    ):
        if mqtt is None:
            raise RuntimeError("paho-mqtt no instalado. Ejecuta: pip install paho-mqtt")
        
        self.printer_ip = printer_ip
        self.serial = serial
        self.access_code = access_code
        self.on_message_callback = on_message
        self.on_connect_callback = on_connect
        self.on_disconnect_callback = on_disconnect
        
        self.client = None
        self.connected = False
        self.last_data = {}
        self.last_update = None
        self._lock = threading.Lock()
        self._pushall_timer = None  # Referencia al timer para cleanup
        self._last_reconnect_attempt = 0
    
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """FIX: Firma correcta para paho-mqtt v2."""
        # En paho-mqtt v2, reason_code es un objeto, no int
        rc = reason_code if isinstance(reason_code, int) else getattr(reason_code, 'value', 0)
        if rc == 0:
            self.connected = True
            logger.info(f"✅ Conectado a {self.printer_ip} (serial: {self.serial})")
            topic = f"device/{self.serial}/report"
            client.subscribe(topic)
            logger.info(f"   Suscrito a: {topic}")
            # FIX: Guardar referencia al timer
            self._pushall_timer = threading.Timer(0.5, self.request_full_status)
            self._pushall_timer.daemon = True
            self._pushall_timer.start()
            if self.on_connect_callback:
                self.on_connect_callback(self.serial)
        else:
            self.connected = False
            logger.error(f"❌ Conexión fallida a {self.printer_ip}: código {rc}")
    
    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        """Firma correcta para paho-mqtt v2: (self, client, userdata, disconnect_flags, reason_code, properties)."""
        rc = reason_code if isinstance(reason_code, int) else getattr(reason_code, 'value', 0)
        self.connected = False
        if rc != 0:
            logger.warning(f"⚠️ Desconexión inesperada de {self.printer_ip} (código {rc})")
        if self.on_disconnect_callback:
            self.on_disconnect_callback(self.serial)
    
    def _on_message(self, client, userdata, msg, properties=None):
        """Callback al recibir mensaje."""
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            with self._lock:
                self.last_data = data
                self.last_update = datetime.now()
            
            # FIX: Log a archivo con rotación
            self._log_to_file(data)
            
            # Log resumen a consola
            mc = data.get("print", {}).get("mc_percent", "N/A")
            stage = data.get("print", {}).get("mc_print_stage", "N/A")
            logger.info(f"📨 {self.serial}: mc_percent={mc}, stage={stage}")
            
            if self.on_message_callback:
                self.on_message_callback(self.serial, data)
                
        except json.JSONDecodeError:
            logger.error(f"Error parseando mensaje de {self.printer_ip}")
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
    
    def _log_to_file(self, data: dict):
        """Log a archivo con rotación para no llenar el disco."""
        try:
            log_handler = self._get_file_handler()
            log_handler.emit(logging.LogRecord(
                name=__name__,
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=f"{datetime.now().isoformat()} | {self.serial} | {json.dumps(data, default=str)}",
                args=(),
                exc_info=None
            ))
        except Exception:
            pass  # Fallo silencioso en logging no crítico
    
    @staticmethod
    def _get_file_handler():
        """Handler de log con rotación (singleton)."""
        if not hasattr(LocalMQTTClient, '_file_handler'):
            handler = RotatingFileHandler(
                "mqtt_debug.log",
                maxBytes=1_000_000,  # 1MB
                backupCount=3,
                encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter('%(message)s'))
            LocalMQTTClient._file_handler = handler
        return LocalMQTTClient._file_handler
    
    def connect(self):
        """Conectar al broker MQTT de la impresora."""
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"bambuPet-{self.serial}"
            )
            
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            # Autenticación local: username=bblp, password=access_code
            self.client.username_pw_set("bblp", self.access_code)
            
            # TLS — desactivar verificación de certificado (BambuLab usa self-signed)
            self.client.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS)
            self.client.tls_insecure_set(True)
            
            # Timeout para conexión (evita bloqueos largos)
            self.client.connect_timeout = 5
            
            logger.info(f"Conectando a {self.printer_ip}:8883...")
            self.client.connect(self.printer_ip, 8883, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Error conectando a {self.printer_ip}: {e}")
            self.connected = False
    
    def disconnect(self):
        """Desconectar del broker de forma segura."""
        if self._pushall_timer and self._pushall_timer.is_alive():
            self._pushall_timer.cancel()
            self._pushall_timer = None
        
        if self.client:
            self.client.loop_stop()
            try:
                self.client.disconnect()
            except Exception:
                pass  # Ignorar errores al desconectar
            self.connected = False
            logger.info(f"Desconectado de {self.printer_ip}")
    
    def get_last_data(self) -> Dict:
        """Obtener último mensaje recibido."""
        with self._lock:
            return self.last_data.copy()
    
    def request_full_status(self):
        """Solicitar estado completo (pushall)."""
        if not self.connected:
            logger.warning(f"No conectado a {self.printer_ip}, no se puede solicitar estado")
            return
        
        command = {"pushing": {"command": "pushall"}}
        topic = f"device/{self.serial}/request"
        payload = json.dumps(command)
        self.client.publish(topic, payload)
        logger.info(f"Pushall enviado a {self.serial}")


class MQTTManager:
    """
    Gestiona múltiples conexiones MQTT a impresoras BambuLab.
    Un cliente por impresora, cada uno en su propio hilo.
    """
    
    def __init__(self, on_state_change: Optional[Callable] = None):
        """
        Args:
            on_state_change: Callback(serial, data) cuando llega un mensaje
        """
        self.clients: Dict[str, LocalMQTTClient] = {}
        self.on_state_change = on_state_change
        self._printer_configs: Dict[str, Dict] = {}
        self._connected_count = 0
        self._count_lock = threading.Lock()
    
    def add_printer(self, config: Dict):
        """
        Agregar una impresora a la configuración.
        
        Args:
            config: Dict con keys: name, ip, serial, access_code
        """
        serial = config['serial']
        self._printer_configs[serial] = config
        logger.info(f"Impresora agregada: {config['name']} ({serial}) @ {config['ip']}")
    
    def remove_printer(self, serial: str):
        """Eliminar una impresora."""
        if serial in self.clients:
            self.clients[serial].disconnect()
            del self.clients[serial]
        self._printer_configs.pop(serial, None)
    
    def start_all(self):
        """Conectar a todas las impresoras configuradas."""
        for serial, config in self._printer_configs.items():
            if serial not in self.clients:
                client = LocalMQTTClient(
                    printer_ip=config['ip'],
                    serial=config['serial'],
                    access_code=config['access_code'],
                    on_message=self._handle_message,
                    on_connect=self._handle_connect,
                    on_disconnect=self._handle_disconnect
                )
                self.clients[serial] = client
                client.connect()
    
    def stop_all(self):
        """Desconectar todas las impresoras."""
        for client in self.clients.values():
            client.disconnect()
        self.clients.clear()
    
    def get_printer_state(self, serial: str) -> Optional[Dict]:
        """Obtener estado de una impresora."""
        if serial in self.clients:
            return self.clients[serial].get_last_data()
        return None
    
    def get_all_states(self) -> Dict[str, Dict]:
        """Obtener estado de todas las impresoras."""
        states = {}
        for serial, client in self.clients.items():
            states[serial] = client.get_last_data()
        return states
    
    def request_all_status(self):
        """Solicitar estado completo a todas las impresoras."""
        for client in self.clients.values():
            client.request_full_status()
    
    def _handle_message(self, serial: str, data: Dict):
        """Mensaje recibido de una impresora."""
        if self.on_state_change:
            self.on_state_change(serial, data)
    
    def _handle_connect(self, serial: str):
        """Conexión exitosa."""
        with self._count_lock:
            self._connected_count += 1
        logger.info(f"🟢 {serial} conectado")
    
    def _handle_disconnect(self, serial: str):
        """Desconexión."""
        with self._count_lock:
            self._connected_count = max(0, self._connected_count - 1)
        logger.warning(f"🔴 {serial} desconectado")
    
    @property
    def connected_count(self) -> int:
        """FIX: Contador incremental en lugar de iterar cada vez."""
        return self._connected_count
    
    @property
    def total_count(self) -> int:
        """Número total de impresoras configuradas."""
        return len(self.clients)
