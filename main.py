"""
bambuPet — Desktop pet para monitoreo de impresoras BambuLab
v0.2 Prototipo con MQTT directo
"""

import sys
import json
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl, QPoint, QRect, QSize
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtGui import QColor, QCursor

from mqtt_manager import MQTTManager
from parser import parse_printer_status, get_print_summary, PrinterStateTracker

# Cargar configuración
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)


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
        self.always_on_top = CONFIG["display"]["always_on_top"]
        
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
        self.resize(self.pet_size, self.pet_size)
        
        # Posición inicial (esquina inferior derecha)
        self._position_window()
    
    def _position_window(self):
        """Posicionar ventana en esquina inferior derecha."""
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.pet_size - CONFIG["display"]["offset_x"]
        y = screen.height() - self.pet_size - CONFIG["display"]["offset_y"]
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
        """Cuando el HTML termina de cargar, inyectar estado."""
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
            printers_ui.append(parsed)
        
        state = {
            "authenticated": self.mqtt_manager.connected_count > 0 if self.mqtt_manager else False,
            "printers": printers_ui,
            "mqtt_status": {
                "connected": self.mqtt_manager.connected_count if self.mqtt_manager else 0,
                "total": self.mqtt_manager.total_count if self.mqtt_manager else 0
            }
        }
        
        js = f"window.bambuPet && window.bambuPet.updateState({json.dumps(state)});"
        self.webview.page().runJavaScript(js)
    
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
        
        if not printers:
            print("[bambuPet] ⚠️ No hay impresoras configuradas en config.json")
            return
        
        self.mqtt_manager = MQTTManager(on_state_change=self._on_mqtt_message)
        
        for printer_conf in printers:
            self.mqtt_manager.add_printer(printer_conf)
        
        # Conectar a todas
        self.mqtt_manager.start_all()
        
        # Timer para solicitar estado completo periódicamente (pushall)
        self.pushall_timer = QTimer()
        self.pushall_timer.timeout.connect(self._request_pushall)
        self.pushall_timer.start(mqtt_config.get("poll_interval_sec", 10) * 1000)
        
        # Timer para reconexión automática
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self._check_reconnect)
        self.reconnect_timer.start(mqtt_config.get("reconnect_delay_sec", 5) * 1000)
    
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
        """Verificar y reconectar impresoras desconectadas."""
        if not self.mqtt_manager:
            return
        
        for serial, client in self.mqtt_manager.clients.items():
            if not client.connected and client.client is not None:
                print(f"[bambuPet] 🔄 Reconectando a {serial}...")
                try:
                    client.connect()
                except Exception as e:
                    print(f"[bambuPet] ❌ Error reconectando: {e}")
    
    # === Interacciones ===
    
    def mousePressEvent(self, event):
        """Click → iniciar drag."""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self.drag_start = event.globalPos()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Mover ventana al arrastrar."""
        if self.dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_offset)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Soltar → toggle expandir si fue click simple."""
        if self.dragging and event.button() == Qt.LeftButton:
            self.dragging = False
            if hasattr(self, 'drag_start'):
                moved = (event.globalPos() - self.drag_start).manhattanLength()
                if moved < 5:
                    self._toggle_expand()
            event.accept()
    
    def _toggle_expand(self):
        """Alternar entre vista compacta y expandida."""
        self.expanded = not self.expanded
        self._compact_mode = not self.expanded
        
        if self.expanded:
            self.resize(self.expanded_size, self.expanded_size + 100)
            # En expandido, el webview recibe clicks (para botones)
            self.webview.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.webview.page().runJavaScript(
                "window.bambuPet && window.bambuPet.expand();"
            )
        else:
            self.resize(self.pet_size, self.pet_size)
            # En compacto, la ventana recibe clicks (para drag)
            self.webview.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.webview.page().runJavaScript(
                "window.bambuPet && window.bambuPet.collapse();"
            )

    def eventFilter(self, obj, event):
        """Redirigir eventos de mouse del webview a la ventana (para drag en compacto)."""
        if self._compact_mode and obj == self.webview:
            if event.type() in (
                event.MouseButtonPress,
                event.MouseButtonRelease,
                event.MouseButtonDblClick,
                event.MouseMove,
            ):
                # Reenviar a la ventana
                QApplication.sendEvent(self, event)
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
    # Habilitar alta densidad de píxeles
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("bambuPet")
    
    window = PandaPetWindow()
    window.show()
    
    print("🐼 bambuPet iniciado — Click en el panda para expandir")
    print("   ESC para cerrar")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
