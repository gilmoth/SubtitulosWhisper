# Subtitulos Whisper

Aplicación de escritorio para Windows que genera transcripciones y subtítulos a partir de archivos de audio y vídeo de forma **local y privada**, usando [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) e interfaz gráfica PySide6.

---

## Características

- Transcripción local sin conexión a Internet (tras descarga del modelo)
- Soporte para archivo individual o carpeta completa (modo batch)
- Exportación a **TXT**, **SRT** y **VTT** simultáneamente
- Detección automática de GPU CUDA (aceleración con tarjeta NVIDIA)
- Selector de modelo con información de velocidad, calidad y VRAM requerida
- Estimación de tiempo antes de iniciar según modelo, dispositivo y duración del audio
- Panel de log en tiempo real integrado en la UI
- Dos barras de progreso: archivo actual y lote completo
- Configuración persistente (preferencias, ventana, último directorio)
- Diálogo de configuración separado con pestañas (Modelo / Dispositivo)
- Directorio de descarga de modelos configurable desde la interfaz

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

## Requisitos

- Python 3.10 o superior
- Windows 10 o superior
- Para aceleración GPU: tarjeta NVIDIA con drivers actualizados y CUDA instalado

## Instalación en desarrollo

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

Los modelos y ffmpeg se descargan automáticamente en `%APPDATA%\SubtitulosWhisper\` la primera vez que se usan. El directorio de descarga de modelos puede cambiarse desde el diálogo de configuración (⚙ Configuración → pestaña Modelo).

---

## Estructura del proyecto

```
Subtitulos_Whisper/
├── main.py                  # Punto de entrada
├── requirements.txt
├── app/
│   ├── config.py            # Configuración persistente (JSON)
│   ├── paths.py             # Rutas de datos de la aplicación
│   ├── batch.py             # Gestión de lotes de archivos
│   ├── transcriber.py       # Motor Faster-Whisper
│   ├── exporter.py          # Exportación TXT/SRT/VTT
│   ├── worker.py            # Hilo QThread de transcripción
│   ├── model_manager.py     # Descarga y gestión de modelos
│   ├── hardware.py          # Detección de GPU/CPU/RAM
│   ├── ffmpeg_manager.py    # Gestión de ffmpeg/ffprobe
│   └── ui/
│       ├── ui_main.py       # Ventana principal PySide6
│       └── settings_dialog.py  # Diálogo de configuración (pestañas Modelo / Dispositivo)
└── tests/
```
