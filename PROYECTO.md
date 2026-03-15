# Subtitulos Whisper — Estado del Proyecto

## Descripción General

Aplicación de escritorio Windows para transcribir audio/vídeo de forma local usando **Faster-Whisper**. Interfaz gráfica con **PySide6**. Soporta archivo individual y modo batch por carpeta, con exportación a TXT, SRT y VTT.

---

## Arquitectura — Módulos

| Módulo | Responsabilidad |
|--------|----------------|
| `main.py` | Punto de entrada. Inicializa QApplication, registra AppUserModelID de Windows, aplica icono y crea la ventana principal. |
| `app/ui/ui_main.py` | Ventana principal. Fila de resumen compacta (modelo/dispositivo), botón "⚙ Configuración", fila de carpeta de salida, task mode (transcribir/traducir/ambos), tabla de batch y dos barras de progreso. |
| `app/ui/settings_dialog.py` | Diálogo de configuración con tres pestañas: "Modelo" (tabla de modelos + descarga + directorio), "Dispositivo" (CPU/CUDA) y "Audio" (VAD, idioma, formato de subtítulos). |
| `app/ui/resources/icon.ico` | Icono de la aplicación. |
| `app/config.py` | Lectura/escritura de `config.json` en `%APPDATA%\SubtitulosWhisper`. |
| `app/paths.py` | Rutas estandarizadas a directorios de datos (modelos, ffmpeg, logs, config). |
| `app/batch.py` | Colección de archivos a procesar: estados, skip de ya transcritos, filtro de extensiones. |
| `app/transcriber.py` | Motor Faster-Whisper: carga modelo, convierte audio a 16kHz mono con ffmpeg, transcribe con callback de progreso por segmento. |
| `app/exporter.py` | Formatea segmentos transcritos a `.txt`, `.srt` y `.vtt`. |
| `app/worker.py` | `TranscriptionWorker` (QThread): ejecuta el pipeline sin bloquear la UI. `TranscriptionJob` incluye `output_dir`, `max_line_chars` y `max_lines_per_segment`. |
| `app/model_manager.py` | Lista, descarga y verifica modelos Whisper. Metadatos (tamaño, velocidad, calidad, VRAM, RTF). Acepta `models_dir` configurable. |
| `app/hardware.py` | Detecta CUDA (vía ctranslate2), número de GPUs, cores CPU y RAM. |
| `app/ffmpeg_manager.py` | Localiza/descarga ffmpeg. `get_audio_duration()` via ffprobe para estimaciones de tiempo. |

---

## Funcionalidades Implementadas

### UI
- [x] Ventana principal PySide6 con tabla de estado del batch
- [x] Modo archivo individual / modo carpeta (batch)
- [x] Checkboxes de formato de salida: TXT, SRT, VTT (al menos uno siempre activo)
- [x] Modo de tarea: Transcribir / Traducir al inglés / Ambos (genera archivos con sufijo `.en` para la traducción)
- [x] Botón Iniciar / Cancelar con control de estado de widgets
- [x] Configuración persistente: tamaño de ventana, modo, directorio, dispositivo, modelo, idioma, VAD, formato
- [x] Indicador de dispositivo activo en status bar (verde si CUDA, gris si CPU)
- [x] **Panel de log desplegable** (`▶ Log` / `▼ Log`): fondo oscuro, monoespaciado, máx. 500 líneas, thread-safe vía señal Qt
- [x] **Dos barras de progreso**: "Archivo" (por segmento, 0–100%) y "Lote" (por archivo completado)
- [x] **Selector de modelo** como tabla (`QTableWidget`): todos los modelos visibles a la vez con radio button de selección, indicador `✓`/`○`, tamaño, velocidad/calidad en estrellas y VRAM. Sin selección por hover.
- [x] **Estimación de tiempo** antes de iniciar: calculada desde duración real del audio (ffprobe) × RTF del modelo, ajustada a CPU o GPU. Color verde/naranja/rojo según duración
- [x] **Diálogo de configuración con tres pestañas** (`⚙ Configuración`): Modelo, Dispositivo y Audio
- [x] **Directorio de descarga de modelos configurable** desde la pestaña "Modelo"
- [x] **Descarga de modelos desde la UI**: botón `⬇ Descargar` habilitado solo si el modelo no está descargado; `_DownloadWorker` (QThread), barra animada, refresco de tabla al terminar
- [x] **Carpeta de salida configurable**: checkbox "Misma carpeta" (por defecto) + browse; persiste en `config.json`; `TranscriptionJob.output_dir`
- [x] **Icono de aplicación**: cargado en `QApplication` y `MainWindow`; AppUserModelID registrado para barra de tareas de Windows
- [x] **Mensaje de finalización**: resumen con ✓ Completados / ✗ Errores / — Cancelados / — Saltados

### Configuración avanzada (pestaña "Audio")
- [x] **VAD configurable**: checkbox con descripción detallada de cuándo usar o no usar el filtro
- [x] **Modo de idioma**: Auto-detectar / Idioma fijo (combo con 12 idiomas) / Multilingüe (detección por segmento)
- [x] **Formato de subtítulos**: límite de caracteres por línea (20–120, default 42) y máximo de líneas por segmento (1–4, default 2); valores almacenados en config y pasados a `TranscriptionJob`

### Transcripción
- [x] Detección CUDA usando ctranslate2 (dependencia real de faster-whisper), sin depender de DLLs hardcodeadas
- [x] Auto-detección CUDA al arrancar; fallback automático a CPU si no disponible
- [x] Selección de dispositivo CPU / CUDA con botón "Detectar hardware" en el diálogo
- [x] Carga lazy del modelo (solo al iniciar transcripción)
- [x] Preprocesado de audio a WAV 16kHz mono con ffmpeg
- [x] Callback de progreso por segmento → barra de archivo en tiempo real
- [x] Soporte VAD, modos de idioma (auto/fijo/multi), traducción al inglés

### Batch
- [x] Skip automático de archivos ya transcritos (comprueba que existan todos los formatos pedidos)
- [x] Estado por archivo: Pendiente / En progreso / Completado / Error / Cancelado / Saltado
- [x] Cancelación controlada (termina el archivo actual antes de parar)

### Infraestructura
- [x] ffmpeg descargado automáticamente si no está en el sistema
- [x] `get_audio_duration()` via ffprobe para estimaciones de duración
- [x] Logging a archivo (`app.log`) y panel UI simultáneamente

---

## Limitaciones Conocidas

- **Estimaciones de tiempo orientativas**: los RTF en `MODEL_METADATA` son medias típicas; varían según hardware específico.
- **Batch skip parcial**: si se cambia la selección de formatos entre ejecuciones puede no detectar archivos parcialmente procesados.
- **Progreso con VAD**: el progreso puede parecer irregular en archivos con mucho silencio.

---

## Próximos Pasos

1. **Empaquetado con PyInstaller** — generar ejecutable `.exe` distribuible con ffmpeg y modelos opcionales embebidos

---

## Requisitos y Dependencias

- Python 3.10+, Windows 10+
- `PySide6` — framework de UI
- `faster-whisper` — motor de transcripción (incluye ctranslate2)
- `requests` — descarga de ffmpeg
- `ffmpeg` / `ffprobe` — conversión de audio y detección de duración (descarga automática)
- GPU NVIDIA + drivers actualizados para aceleración CUDA (opcional)

---

## Historial de Cambios Relevantes

| Fecha | Cambio |
|-------|--------|
| 2026-03-14 | Detección CUDA migrada de `ctypes.CDLL("cublas64_12.dll")` a `ctranslate2.get_cuda_device_count()` — soluciona fallo en CUDA 13 y DLLs no en PATH |
| 2026-03-14 | Panel de log desplegable integrado en UI con handler thread-safe |
| 2026-03-14 | Dos barras de progreso: archivo actual (por segmento) y lote (por archivo) |
| 2026-03-14 | Indicador de dispositivo activo en status bar con estados idle/running/done |
| 2026-03-14 | Selector de modelo con metadatos visuales (tamaño, velocidad, calidad, VRAM) |
| 2026-03-14 | Estimación de tiempo previa a transcripción basada en ffprobe + RTF por modelo/dispositivo |
| 2026-03-14 | Configuración movida a diálogo separado (`settings_dialog.py`) con pestañas Modelo/Dispositivo. Ventana principal reducida a fila de resumen compacta. ModelManager acepta `models_dir` configurable. |
| 2026-03-14 | Selector de modelo reemplazado por `QTableWidget` con radio buttons: todos los modelos visibles a la vez, sin cambio accidental por hover. |
| 2026-03-14 | Descarga de modelos desde la UI: `_DownloadWorker` (QThread), barra animada, refresco de tabla al terminar. |
| 2026-03-14 | Carpeta de salida configurable: checkbox "Misma carpeta" + browse; `TranscriptionJob.output_dir`; el worker crea el directorio si no existe. |
| 2026-03-14 | Icono de aplicación integrado; AppUserModelID registrado para barra de tareas de Windows. |
| 2026-03-14 | Pestaña "Audio" en diálogo de configuración: VAD, modo de idioma (auto/fijo/multi + combo 12 idiomas), formato de subtítulos (chars/línea y líneas/segmento). Valores pasados a `TranscriptionJob`. |
| 2026-03-15 | `_wrap_text()` implementado en `exporter.py`; `export_srt()` y `export_vtt()` aplican `max_line_chars` y `max_lines_per_segment` al generar subtítulos. |
