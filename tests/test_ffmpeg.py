"""Prueba rápida para el gestor de FFMPEG.

Este script:
- Llama a ensure_ffmpeg() mostrando progreso en consola.
- Imprime la ruta final donde está ffmpeg.exe.
- Ejecuta 'ffmpeg -version' y muestra la primera línea.
- Imprime 'OK' si todo funciona.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

from app.ffmpeg_manager import FFmpegManager


def _progress(downloaded: int, total: int) -> None:
    """Callback de progreso que muestra bytes descargados en consola."""
    if total > 0:
        percent = downloaded * 100 // total
        print(f"Descarga FFMPEG: {percent}% ({downloaded}/{total} bytes)")
    else:
        print(f"Descarga FFMPEG: {downloaded} bytes")


def main() -> None:
    """Ejecuta la prueba básica del gestor de FFMPEG."""
    manager = FFmpegManager()

    path = manager.ensure_ffmpeg(progress_callback=_progress)
    if path is None:
        print("No se pudo preparar FFMPEG.")
        return

    print(f"FFMPEG path: {path}")

    try:
        proc = subprocess.run(
            [str(path), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
        first_line = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
        print("ffmpeg -version:", first_line)
    except Exception as exc:
        print(f"Error al ejecutar 'ffmpeg -version': {exc}")
        return

    print("OK")


if __name__ == "__main__":
    main()

