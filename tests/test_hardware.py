"""Prueba rápida para el detector de hardware.

Este script:
- Instancia HardwareDetector.
- Imprime el perfil completo de hardware detectado.
- Imprime el dispositivo recomendado.
- Imprime 'OK' si termina sin errores.
"""

from __future__ import annotations

from app.hardware import HardwareDetector


def main() -> None:
    """Ejecuta la prueba básica del detector de hardware."""
    detector = HardwareDetector()

    profile = detector.get_hardware_profile()
    print("Hardware profile:", profile)

    recommended = detector.get_recommended_device()
    print("Recommended device:", recommended)

    print("OK")


if __name__ == "__main__":
    main()

