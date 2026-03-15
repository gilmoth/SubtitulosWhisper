# Subtitulos Whisper

Aplicación de escritorio para Windows que genera transcripciones y subtítulos a partir de archivos de audio y vídeo de forma **local y privada**, usando [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) e interfaz gráfica PySide6.

---

## Capturas de pantalla

> *(pendiente de añadir capturas)*

---

## Características

- Transcripción local sin conexión a Internet (tras descarga del modelo)
- Soporte para archivo individual o carpeta completa (modo batch)
- Exportación a **TXT**, **SRT** y **VTT** simultáneamente
- Detección automática de GPU CUDA (aceleración con tarjeta NVIDIA)
- Selector de modelo con información de velocidad, calidad y VRAM requerida
- Estimación de tiempo antes de iniciar según modelo, dispositivo y duración del audio
- Modos de tarea: Transcribir / Traducir al inglés / Ambos
- Configuración de VAD, idioma y formato de subtítulos (chars/línea, líneas/segmento)
- Panel de log en tiempo real con colores por nivel de mensaje
- Botón limpiar lista en la barra de estado
- Configuración persistente (preferencias, ventana, último directorio)
- Distribuible como ejecutable `.exe` sin necesidad de instalar Python

## Formatos de entrada soportados

`wav · mp3 · mp4 · m4a · flac · ogg · mkv · avi · mov · webm · wma · aac`

## Modelos disponibles

| Modelo    | Tamaño  | Velocidad | Calidad   | VRAM aprox. |
|-----------|---------|-----------|-----------|-------------|
| tiny      | ~75 MB  | ●●●●●     | ●●○○○     | ~1 GB       |
| base      | ~145 MB | ●●●●○     | ●●●○○     | ~1 GB       |
| small     | ~465 MB | ●●●○○     | ●●●●○     | ~2 GB       |
| medium    | ~1.5 GB | ●●○○○     | ●●●●●     | ~5 GB       |
| large-v2  | ~3 GB   | ●○○○○     | ●●●●●     | ~10 GB      |
| large-v3  | ~3 GB   | ●○○○○     | ●●●●●     | ~10 GB      |

---

## Cómo usar (ejecutable)

1. Descarga la carpeta `SubtitulosWhisper/` de la sección de releases.
2. Ejecuta `SubtitulosWhisper.exe` — no requiere instalación.
3. En **⚙ Configuración → Modelo**, descarga el modelo que prefieras.
4. Selecciona un archivo o carpeta de entrada.
5. Elige los formatos de salida (TXT / SRT / VTT) y la tarea (Transcribir / Traducir).
6. Pulsa **▶ Iniciar**.

Los modelos y ffmpeg se descargan automáticamente en `%APPDATA%\SubtitulosWhisper\` la primera vez que se usan.

---

## Requisitos

- Windows 10 o superior (64-bit)
- Para aceleración GPU: tarjeta **NVIDIA** con drivers actualizados (CUDA 11.x o superior)
- Sin GPU: funciona en CPU, más lento según el modelo elegido

---

## Instalación en desarrollo

```bash
git clone <url-del-repo>
cd Subtitulos_Whisper
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Empaquetado

```bash
venv\Scripts\activate
pyinstaller -y SubtitulosWhisper.spec
# Resultado en dist/SubtitulosWhisper/
```

---

## Estructura del proyecto

```
Subtitulos_Whisper/
├── main.py                     # Punto de entrada
├── requirements.txt
├── SubtitulosWhisper.spec      # Configuración de PyInstaller
├── app/
│   ├── config.py               # Configuración persistente (JSON)
│   ├── paths.py                # Rutas de datos de la aplicación
│   ├── batch.py                # Gestión de lotes de archivos
│   ├── transcriber.py          # Motor Faster-Whisper
│   ├── exporter.py             # Exportación TXT/SRT/VTT
│   ├── worker.py               # Hilo QThread de transcripción
│   ├── model_manager.py        # Descarga y gestión de modelos
│   ├── hardware.py             # Detección de GPU/CPU/RAM
│   ├── ffmpeg_manager.py       # Gestión de ffmpeg/ffprobe
│   └── ui/
│       ├── ui_main.py          # Ventana principal PySide6
│       ├── settings_dialog.py  # Diálogo de configuración
│       └── resources/
│           └── icon.ico
└── tests/
```

---

## Licencia

MIT — ver [LICENSE](LICENSE).
