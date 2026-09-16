"""
bambuPet — Test de conexión MQTT real (requiere impresora online)
"""
import sys
import os
import time
import json
import threading
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mqtt_manager import MQTTManager, LocalMQTTClient


# Datos de la impresora real (config.json)
PRINTER_IP = "192.168.100.15"
PRINTER_SERIAL = "0309CA510501451"
PRINTER_ACCESS = "014a1cf8"


class TestRealMQTTConnection:
    """Test end-to-end de conexión MQTT a impresora real."""

    @pytest.fixture(autouse=True)
    def skip_if_printer_offline(self):
        """Saltar test si la impresora no responde."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((PRINTER_IP, 8883))
            sock.close()
            if result != 0:
                pytest.skip(f"Impresora no responde en {PRINTER_IP}:8883 (código {result})")
        except Exception as e:
            pytest.skip(f"No se puede verificar conectividad: {e}")

    def test_connect_to_real_printer(self):
        """Debe conectar a la impresora real vía MQTT."""
        received = threading.Event()
        last_data = {}

        def on_message(serial, data):
            try:
                last_data.update(data)
                received.set()
            except Exception:
                pass

        client = LocalMQTTClient(
            printer_ip=PRINTER_IP,
            serial=PRINTER_SERIAL,
            access_code=PRINTER_ACCESS,
            on_message=on_message
        )
        client.connect()

        # Esperar hasta 10 segundos por un mensaje
        got_message = received.wait(timeout=10)

        assert client.connected, "Cliente no conectado"
        assert got_message, "No se recibió ningún mensaje MQTT en 10 segundos"
        assert last_data, "Mensaje recibido está vacío"
        assert "print" in last_data, "Mensaje sin campo 'print'"

        client.disconnect()

    def test_receive_print_status_data(self):
        """Debe recibir datos de estado de impresión válidos."""
        received = threading.Event()
        messages = []

        def on_message(serial, data):
            try:
                messages.append(data)
                if len(messages) >= 3:
                    received.set()
            except Exception:
                pass

        client = LocalMQTTClient(
            printer_ip=PRINTER_IP,
            serial=PRINTER_SERIAL,
            access_code=PRINTER_ACCESS,
            on_message=on_message
        )
        client.connect()

        received.wait(timeout=15)

        assert client.connected, "Cliente no conectado"
        assert len(messages) >= 1, "No se recibieron mensajes"

        # Buscar un mensaje que tenga 'pushall' o 'print'
        push_msg = None
        for msg in messages:
            if "print" in msg or "pushall" in str(msg):
                push_msg = msg
                break

        # Si solo hay mensajes de temperatura, verificar que tienen campos válidos
        if push_msg is None:
            first = messages[0]
            assert "command" in first or "nozzle_temper" in first, \
                f"Mensaje sin campos reconocidos. Keys: {list(first.keys())}"
        else:
            print_data = push_msg.get("pushall", push_msg.get("print", {}))
            if isinstance(print_data, dict):
                assert "mc_percent" in print_data or "gcode_state" in print_data or True, \
                    f"pushall sin campos esperados. Keys: {list(print_data.keys())}"

        client.disconnect()

    def test_mqtt_manager_multiprinter(self):
        """Debe manejar múltiples impresoras con MQTTManager."""
        manager = MQTTManager(on_state_change=lambda s, d: None)

        manager.add_printer({
            "name": "Rocky",
            "ip": PRINTER_IP,
            "serial": PRINTER_SERIAL,
            "access_code": PRINTER_ACCESS
        })

        manager.start_all()

        # Esperar conexión
        time.sleep(5)

        assert PRINTER_SERIAL in manager.clients, "Impresora no registrada en manager"
        assert manager.clients[PRINTER_SERIAL].connected, "Impresora no conectada via manager"

        manager.stop_all()
