"""Punto de entrada de la aplicación Subtitulos Whisper.

Este módulo inicializa la aplicación de escritorio basada en PySide6,
configura el sistema de logging y crea la ventana principal.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import Config
from app.paths import get_logs_dir
from app.ui.ui_main import MainWindow


def _setup_logging(logs_dir: Path) -> None:
    """Configura el logging de la aplicación para escribir en un archivo."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _get_icon_path() -> str:
    """Devuelve la ruta al icono tanto en desarrollo como en exe de PyInstaller."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent
    return str(base / "app" / "ui" / "resources" / "icon.ico")


def main() -> None:
    """Inicializa QApplication y la ventana principal de la aplicación.

    Responsabilidad: coordinar el arranque de la aplicación, cargar la
    configuración, configurar logging y mostrar la ventana principal.
    """
    app = QApplication(sys.argv)

    # Registrar AppUserModelID para que Windows muestre el icono correcto en la barra de tareas.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SubtitulosWhisper.App")
    except Exception:
        pass

    app.setWindowIcon(QIcon(_get_icon_path()))

    # Cargar configuración (incluye creación de config.json con valores por defecto).
    config = Config()

    # Configurar logging a archivo en el directorio de logs de la aplicación.
    logs_dir = get_logs_dir()
    _setup_logging(logs_dir)

    # Crear y mostrar la ventana principal.
    window = MainWindow()
    window.show()

    # Ejecutar el bucle de eventos hasta el cierre de la ventana.
    exit_code = app.exec()

    # Guardar cualquier cambio pendiente en la configuración antes de salir.
    config.save()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

