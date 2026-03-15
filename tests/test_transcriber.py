"""Prueba rápida para el transcriptor basado en Faster-Whisper.

Este script:
- Detecta si CUDA está disponible y elige 'cuda' o 'cpu'.
- Asegura que ffmpeg está instalado y disponible.
- Crea un Transcriber con el modelo 'tiny'.
- Pide al usuario una ruta de archivo de audio o vídeo.
- Transcribe el archivo con language_mode 'auto'.
- Imprime los primeros 3 segmentos con sus tiempos.
- Imprime el idioma detectado y la duración total.
- Imprime 'OK' si todo funciona.
"""

from __future__ import annotations

from pathlib import Path

from app.hardware import HardwareDetector
from app.ffmpeg_manager import FFmpegManager
from app.model_manager import ModelManager
from app.transcriber import Transcriber


def main() -> None:
    """Ejecuta la prueba básica del transcriptor."""
    # Forzar uso de CUDA en este test independientemente del hardware disponible.
    detector = HardwareDetector()
    device = "cuda"
    print(f"Dispositivo utilizado para el modelo (forzado): {device}")

    # Asegurar ffmpeg.
    ffmpeg_manager = FFmpegManager()
    ffmpeg_path = ffmpeg_manager.ensure_ffmpeg()
    if ffmpeg_path is None:
        print("No se pudo preparar FFMPEG, abortando prueba de transcripción.")
        return
    print(f"Usando ffmpeg en: {ffmpeg_path}")

    # Preparar gestor de modelos y transcriptor.
    model_manager = ModelManager()
    transcriber = Transcriber(
        model_name="tiny",
        device=device,
        compute_type="auto",
        model_manager=model_manager,
        ffmpeg_path=str(ffmpeg_path),
    )

    # Ruta de archivo fija solicitada
    file_path = Path(r"E:\Descargas\prueba.mp4")
    if not file_path.is_file():
        print(f"El archivo proporcionado no existe: {file_path}")
        return

    options = {
        "language_mode": "auto",
        "language_code": "",
        "vad_enabled": False,
        "mode": "transcribe",
    }

    result = transcriber.transcribe(str(file_path), options)

    segments = result.get("segments", [])
    detected_language = result.get("detected_language", "")
    duration = result.get("duration", 0.0)

    print("\nPrimeros 3 segmentos:")
    for seg in segments[:3]:
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        text = seg.get("text", "")
        lang = seg.get("language", "")
        print(f"[{start:7.2f} -> {end:7.2f}] ({lang}) {text}")

    print(f"\nIdioma detectado: {detected_language}")
    print(f"Duración total (s): {duration:.2f}")

    print("OK")


if __name__ == "__main__":
    main()

