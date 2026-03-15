"""Gestión centralizada de rutas para Subtitulos Whisper.

Responsabilidad: resolver directorios base (APPDATA, modelos, ffmpeg,
logs, etc.) de forma consistente y reutilizable en toda la aplicación.
"""

from __future__ import annotations

from pathlib import Path
import os


APP_DIR_NAME = "SubtitulosWhisper"


def _ensure_dir(path: Path) -> Path:
    """Crea el directorio indicado si no existe y lo devuelve."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_appdata_base_dir() -> Path:
    """Devuelve el directorio base en %APPDATA% para la aplicación.

    La ruta resultante es %APPDATA%\\SubtitulosWhisper en sistemas Windows.
    En otros sistemas, se utiliza un directorio oculto en el HOME como
    fallback para facilitar pruebas fuera de Windows.
    """
    appdata = os.getenv("APPDATA")
    if appdata:
        base = Path(appdata) / APP_DIR_NAME
    else:
        # Fallback genérico para entornos no Windows.
        base = Path.home() / f".{APP_DIR_NAME}"
    return _ensure_dir(base)


def get_config_path() -> Path:
    """Devuelve la ruta absoluta al archivo de configuración JSON.

    La función garantiza que el directorio base de la aplicación exista.
    """
    base_dir = get_appdata_base_dir()
    return base_dir / "config.json"


def get_models_dir() -> Path:
    """Devuelve el directorio donde se almacenan los modelos Whisper.

    Crea el directorio si no existe.
    """
    base_dir = get_appdata_base_dir()
    return _ensure_dir(base_dir / "models")


def get_ffmpeg_dir() -> Path:
    """Devuelve el directorio destinado a la instalación de FFMPEG.

    Crea el directorio si no existe.
    """
    base_dir = get_appdata_base_dir()
    return _ensure_dir(base_dir / "ffmpeg")


def get_logs_dir() -> Path:
    """Devuelve el directorio donde se almacenarán los logs de la aplicación.

    Crea el directorio si no existe.
    """
    base_dir = get_appdata_base_dir()
    return _ensure_dir(base_dir / "logs")


