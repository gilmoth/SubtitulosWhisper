"""Prueba rápida para el gestor de configuración.

Este script:
- Instancia Config.
- Lee y modifica un valor.
- Guarda y vuelve a cargar para verificar la persistencia.
- Imprime 'OK' si todo funciona correctamente.
"""

from __future__ import annotations

from app.config import Config


def main() -> None:
    """Ejecuta la prueba básica del gestor de configuración."""
    cfg = Config()

    original_mode = cfg.get("preferences.mode")
    cfg.set("preferences.mode", "transcribe")
    cfg.save()

    # Volver a cargar desde disco para comprobar persistencia.
    cfg_reloaded = Config()
    reloaded_mode = cfg_reloaded.get("preferences.mode")

    if reloaded_mode != "transcribe":
        raise AssertionError("La configuración no se ha persistido correctamente.")

    # Restaurar el valor original para no dejar el archivo modificado.
    cfg_reloaded.set("preferences.mode", original_mode)
    cfg_reloaded.save()

    print("OK")


if __name__ == "__main__":
    main()

