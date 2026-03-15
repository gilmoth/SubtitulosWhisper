"""Prueba rápida para el gestor de modelos Whisper.

Este script:
- Muestra la lista de modelos disponibles.
- Muestra cuáles están ya descargados.
- Descarga el modelo 'tiny' si no está descargado, mostrando progreso.
- Imprime la ruta final del modelo 'tiny'.
- Imprime 'OK' si todo funciona.
"""

from __future__ import annotations

from app.model_manager import ModelManager, AVAILABLE_MODELS


def _progress(percent: float, message: str) -> None:
    """Callback de progreso que muestra el avance en consola."""
    print(f"{percent:6.2f}% - {message}")


def main() -> None:
    """Ejecuta la prueba básica del gestor de modelos."""
    manager = ModelManager()

    print("Modelos soportados:", AVAILABLE_MODELS)

    downloaded = manager.get_downloaded_models()
    print("Modelos ya descargados:", downloaded)

    tiny_info_before = manager.get_model_info("tiny")
    print("Información inicial del modelo 'tiny':", tiny_info_before)

    path = manager.ensure_model("tiny", progress_callback=_progress)
    if path is None:
        print("No se pudo asegurar el modelo 'tiny'.")
        return

    print(f"Ruta final del modelo 'tiny': {path}")

    tiny_info_after = manager.get_model_info("tiny")
    print("Información final del modelo 'tiny':", tiny_info_after)

    print("OK")


if __name__ == "__main__":
    main()

