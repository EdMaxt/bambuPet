# 🐼 bambuPet — Prototipo v0.1

> Desktop pet para monitoreo de impresoras BambuLab

## Estructura

```
bambuPet/
├── main.py              # Ventana PyQt5 transparente + always-on-top
├── bambu_client.py      # Cliente BambuLab Cloud API
├── config.json          # Configuración usuario
├── static/
│   ├── index.html       # UI del pet (HTML/CSS/JS)
│   ├── style.css        # Estilos + animaciones
│   └── app.js           # Lógica frontend
└── requirements.txt
```

## Uso

```bash
pip install -r requirements.txt
python main.py
```

## Configurar

Edita `config.json` con tus credenciales BambuLab:

```json
{
  "bambu": {
    "username": "tu@email.com",
    "password": "tu-password",
    "region": "ww"
  }
}
```

## Features prototipo

- ✅ Ventana transparente real (PyQt5 + WA_TranslucentBackground)
- ✅ Always-on-top, frameless, draggable
- ✅ Panda pixel-art dibujado en CSS (sin imágenes externas)
- ✅ Click → expandir panel con estado de impresoras
- ✅ Celebración al completar impresión (bounce + confetti)
- ✅ Conexión BambuLab Cloud API
