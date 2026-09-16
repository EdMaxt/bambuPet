"""
bambuPet — Desktop pet para monitoreo de impresoras BambuLab
v0.3.1 — Code review fixes
"""

import sys
import json
import os
import logging
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl, QPoint, QRect, QSize
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtGui import QColor, QCursor

from mqtt_manager import MQTTManager
from parser import parse_printer_status, get_print_summary, PrinterStateTracker

# Configuración de logging (no usar basicConfig en módulo)
logger = logging.getLogger(__name__)

# Cargar configuración con manejo de errores
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    """Cargar configuración con defaults seguros."""
    defaults = {
        "mqtt": {"poll_interval_sec": 10, "reconnect_delay_sec": 5, "printers": []},
        "display": {"position": "bottom-right", "offset_x": 20, "offset_y": 20, "scale": 1.0, "opacity": 0.95, "always_on_top": True},
        "pet": {"celebration_duration_sec": 5, "show_printer_name": True, "compact_mode": "most_progress"}
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        # Merge con defaults
        for key, value in defaults.items():
            if key not in user_config:
                user_config[key] = value
            elif isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if subkey not in user_config[key]:
                        user_config[key][subkey] = subvalue
        return user_config
    except FileNotFoundError:
        logger.warning(f"config.json no encontrado en {CONFIG_PATH}, usando defaults")
        return defaults
    except json.JSONDecodeError as e:
        logger.error(f"config.json inválido: {e}, usando defaults")
        return defaults
    except Exception as e:
        logger.error(f"Error cargando config: {e}, usando defaults")
        return defaults

CONFIG = load_config()


class PandaPetWindow(QMainWindow):
    """Ventana principal del pet — transparente, frameless, always-on-top."""
    
    # Señales para comunicación thread-safe con UI
    update_ui = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.mqtt_manager = None
        self.printer_states = {}
        self.state_trackers = {}  # PrinterStateTracker por serial
        self.expanded = False
        self.dragging = False
        self.drag_offset = QPoint()
        self.drag_start = QPoint()  # Inicializado en __init__ para evitar hasattr
        self.always_on_top = CONFIG["display"]["always_on_top"]
        self._scale = 1.0
        self._opacity = 0.95
        
        self._setup_window()
        self._setup_ui()
        self._setup_mqtt()
    
    def _setup_window(self):
        """Configurar ventana transparente y frameless."""
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool  # No aparece en taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        
        # Tamaño inicial (30% más grande: 120 -> 156)
        self.pet_size = 156
        self.expanded_size = 380
        
        # Aplicar scale y opacity de config
        display = CONFIG.get("display", {})
        self._scale = display.get("scale", 1.0)
        self._opacity = display.get("opacity", 0.95)
        
        size = int(self.pet_size * self._scale)
        self.resize(size, size)
        self.setWindowOpacity(self._opacity)
        
        # Posición inicial (esquina inferior derecha)
        self._position_window()
    
    def _position_window(self):
        """Posicionar ventana en esquina inferior derecha."""
        screen = QApplication.primaryScreen().availableGeometry()
        size = int(self.pet_size * self._scale)
        x = screen.width() - size - CONFIG["display"]["offset_x"]
        y = screen.height() - size - CONFIG["display"]["offset_y"]
        self.move(x, y)
    
    def _setup_ui(self):
        """Crear interfaz con QWebEngineView para renderizar HTML."""
        self.central = QWidget()
        self.setCentralWidget(self.central)
        
        # Layout principal
        self.layout = QVBoxLayout(self.central)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # WebEngineView para renderizar el pet HTML/CSS/JS
        self.webview = QWebEngineView()
        self.webview.setContextMenuPolicy(Qt.NoContextMenu)
        self.webview.page().javaScriptConsoleMessage = self._on_js_console_message
        
        # Hacer el fondo del webview transparente
        page = self.webview.page()
        page.setBackgroundColor(QColor(0, 0, 0, 0))
        
        # Event filter para manejar clicks: compacto → ventana, expandido → webview
        self.webview.installEventFilter(self)
        self._compact_mode = True

        # Cargar HTML del pet
        html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        self.webview.load(QUrl.fromLocalFile(html_path))
        
        self.layout.addWidget(self.webview)
        
        # Conectar señal de carga para inyectar estado inicial
        self.webview.loadFinished.connect(self._on_load_finished)
    
    def _on_load_finished(self):
        """Cuando el HTML termina de cargar, inyectar estado y API."""
        # Inyectar API para comunicación frontend→Python
        js_api = """
        window.bambuPetAPI = {
            receive_message: function(action, value) {
                console.log('bambuPet:' + action + ':' + value);
            }
        };
        """
        self.webview.page().runJavaScript(js_api)
        self._inject_state()
    
    def _inject_state(self):
        """Inyectar estado actual de impresoras en el frontend."""
        # Convertir estados crudos a formato UI usando trackers
        printers_ui = []
        for serial, raw in self.printer_states.items():
            tracker = self.state_trackers.get(serial)
            if tracker:
                parsed = tracker.update(raw)
            else:
                parsed = parse_printer_status(raw)
                config = self._get_printer_config(serial)
                parsed["name"] = config.get("name", "Printer") if config else "Printer"
            
            parsed["serial"] = serial
            
            # FIX: No enviar raw_data completo al frontend (innecesario y pesado)
            parsed.pop("raw", None)
            
            printers_ui.append(parsed)
        
        # FIX: Contadores incrementales en lugar de iterar cada vez
        connected = sum(1 for c in self.mqtt_manager.clients.values() if c.connected) if self.mqtt_manager else 0
        total = len(self.mqtt_manager.clients) if self.mqtt_manager else 0
        
        state = {
            "authenticated": connected > 0,
            "printers": printers_ui,
            "mqtt_status": {
                "connected": connected,
                "total": total
            }
        }
        
        try:
            json_state = json.dumps(state, default=str)
            js = f"window.bambuPet && window.bambuPet.updateState({json_state});"
            self.webview.page().runJavaScript(js)
        except Exception as e:
            logger.error(f"Error inyectando estado: {e}")
    
    def _get_printer_config(self, serial: str) -> dict:
        """Obtener configuración de una impresora por serial."""
        for p in CONFIG.get("mqtt", {}).get("printers", []):
            if p.get("serial") == serial:
                return p
        return {}
    
    def _setup_mqtt(self):
        """Iniciar conexiones MQTT a las impresoras."""
        mqtt_config = CONFIG.get("mqtt", {})
        printers = mqtt_config.get("printers", [])
        
        # FIX: Validar que printers sea una lista
        if not isinstance(printers, list) or not printers:
            logger.warning("No hay impresoras configuradas en config.json")
            return
        
        # FIX: Validar cada impresora
        required_keys = {"name", "ip", "serial", "access_code"}
        valid_printers = []
        for p in printers:
            missing = required_keys - set(p.keys())
            if missing:
                logger.warning(f"Impresora inválida, faltan campos {missing}: {p}")
            else:
                valid_printers.append(p)
        
        if not valid_printers:
            logger.error("No hay impresoras válidas configuradas")
            return
        
        self.mqtt_manager = MQTTManager(on_state_change=self._on_mqtt_message)
        
        for printer_conf in valid_printers:
            self.mqtt_manager.add_printer(printer_conf)
        
        # Conectar a todas
        self.mqtt_manager.start_all()
        
        # Timer para solicitar estado completo periódicamente (pushall)
        self.pushall_timer = QTimer()
        self.pushall_timer.timeout.connect(self._request_pushall)
        self.pushall_timer.start(mqtt_config.get("poll_interval_sec", 10) * 1000)
        
        # Timer para reconexión automática (con backoff exponencial)
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self._check_reconnect)
        self.reconnect_timer.start(mqtt_config.get("reconnect_delay_sec", 5) * 1000)
        self._reconnect_attempts = {}  # Backoff por impresora
    
    def _on_mqtt_message(self, serial: str, raw_data: dict):
        """Mensaje MQTT recibido de una impresora."""
        self.printer_states[serial] = raw_data
        
        # Crear tracker si no existe
        if serial not in self.state_trackers:
            config = self._get_printer_config(serial)
            name = config.get("name", "Printer") if config else "Printer"
            self.state_trackers[serial] = PrinterStateTracker(name=name)
        
        # Actualizar UI en el hilo principal
        self._inject_state()
    
    def _request_pushall(self):
        """Solicitar estado completo a todas las impresoras."""
        if self.mqtt_manager:
            self.mqtt_manager.request_all_status()
    
    def _check_reconnect(self):
        """Verificar y reconectar impresoras desconectadas con backoff exponencial."""
        if not self.mqtt_manager:
            return
        
        for serial, client in self.mqtt_manager.clients.items():
            if not client.connected and client.client is not None:
                # Backoff exponencial: 5s, 10s, 20s, máx 60s
                attempts = self._reconnect_attempts.get(serial, 0)
                delay = min(5 * (2 ** attempts), 60)
                
                # Solo reconectar si pasó el tiempo de backoff
                import time
                last_attempt = getattr(client, '_last_reconnect_attempt', 0)
                if time.time() - last_attempt >= delay:
                    logger.info(f"🔄 Reconectando a {serial} (intento {attempts + 1}, delay {delay}s)...")
                    try:
                        client._last_reconnect_attempt = time.time()
                        client.connect()
                        self._reconnect_attempts[serial] = attempts + 1
                    except Exception as e:
                        logger.error(f"❌ Error reconectando a {serial}: {e}")
                        self._reconnect_attempts[serial] = attempts + 1
            else:
                # Resetear contador si está conectado
                self._reconnect_attempts.pop(serial, None)
    
    # === Interacciones ===
    
    def mousePressEvent(self, event):
        """Drag manejado exclusivamente por eventFilter."""
        pass

    def mouseMoveEvent(self, event):
        """Drag manejado exclusivamente por eventFilter."""
        pass

    def mouseReleaseEvent(self, event):
        """Drag manejado exclusivamente por eventFilter."""
        pass
    
    def _on_js_console_message(self, level, message, line, source):
        """Capturar mensajes del frontend (sliders, etc.)."""
        if message.startswith("bambuPet:"):
            parts = message.split(":", 2)  # FIX: maxsplit=2 para valores con ":"
            if len(parts) >= 3:
                action = parts[1]
                value = parts[2]
                if action == "scale":
                    try:
                        self._scale = float(value) / 100.0
                        if not self.expanded:
                            size = int(self.pet_size * self._scale)
                            self.resize(size, size)
                            self._position_window()
                    except ValueError:
                        pass
                elif action == "opacity":
                    try:
                        self._opacity = float(value) / 100.0
                        self.setWindowOpacity(self._opacity)
                    except ValueError:
                        pass
    
    def _toggle_expand(self):
        """Alternar entre vista compacta y expandida."""
        self.expanded = not self.expanded
        self._compact_mode = not self.expanded
        
        if self.expanded:
            self.resize(self.expanded_size, self.expanded_size + 100)
            self.webview.page().runJavaScript(
                "window.bambuPet && window.bambuPet.expand();"
            )
        else:
            size = int(self.pet_size * self._scale)
            self.resize(size, size)
            self.webview.page().runJavaScript(
                "window.bambuPet && window.bambuPet.collapse();"
            )

    def eventFilter(self, obj, event):
        """Manejar drag directamente desde el eventFilter (sin reenviar eventos)."""
        if self._compact_mode and obj == self.webview:
            # FIX: Verificar que sea evento de mouse antes de acceder a globalPos()
            from PyQt5.QtCore import QEvent
            
            event_type = event.type()
            if event_type not in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.MouseMove,
            ):
                return False
            
            # Ahora es seguro acceder a globalPos()
            global_pos = event.globalPos()
            
            if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                self.dragging = True
                self.drag_offset = global_pos - self.frameGeometry().topLeft()
                self.drag_start = global_pos
                return True
            elif event_type == QEvent.Type.MouseMove and self.dragging:
                if event.buttons() == Qt.LeftButton:
                    new_pos = global_pos - self.drag_offset
                    self.move(new_pos)
                return True
            elif event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
                self.dragging = False
                moved = (global_pos - self.drag_start).manhattanLength()
                if moved < 5:
                    self._toggle_expand()
                return True
            elif event_type == QEvent.Type.MouseButtonDblClick:
                self._toggle_expand()
                return True
        return False
    
    def keyPressEvent(self, event):
        """ESC → cerrar."""
        if event.key() == Qt.Key_Escape:
            self.close()
    
    def closeEvent(self, event):
        """Limpiar recursos al cerrar."""
        if self.mqtt_manager:
            self.mqtt_manager.stop_all()
        event.accept()


def main():
    """Entry point."""
    # Configurar logging solo si no está configurado
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    
    # Habilitar alta densidad de píxeles
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("bambuPet")
    
    window = PandaPetWindow()
    window.show()
    
    logger.info("🐼 bambuPet iniciado — Click en el panda para expandir")
    logger.info("   ESC para cerrar")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
