"""Gestión de configuración persistente para Subtitulos Whisper.

Responsabilidad: leer y escribir el archivo JSON de configuración
ubicado en %APPDATA%\\SubtitulosWhisper\\config.json con valores
por defecto seguros y tipados.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import json

from .paths import get_config_path, get_models_dir, get_ffmpeg_dir, get_logs_dir


class Config:
    """Gestor de configuración de la aplicación.

    Responsabilidad: ofrecer una API centralizada para acceder y
    modificar la configuración persistente de la aplicación mediante
    un archivo JSON en %APPDATA%\\SubtitulosWhisper\\config.json.
    """

    def __init__(self) -> None:
        """Inicializa el gestor de configuración y carga los datos."""
        self._path: Path = get_config_path()
        self._data: Dict[str, Any] = {}
        self._load_or_initialize()

    # ------------------------------------------------------------------
    # Inicialización y carga
    # ------------------------------------------------------------------
    def _default_config(self) -> Dict[str, Any]:
        """Devuelve la configuración por defecto completa."""
        return {
            "version": "1.0",
            "ui": {
                "window_width": 1200,
                "window_height": 800,
                "is_maximized": False,
                "theme": "system",
            },
            "paths": {
                "last_input_path": "",
                "last_output_path": "",
                "output_dir": "",          # vacío = misma carpeta que el audio
                "ffmpeg_path": "",
                "models_dir": str(get_models_dir()),
                "logs_dir": str(get_logs_dir()),
            },
            "preferences": {
                "mode": "both",  # txt + srt + vtt por defecto
                "language_mode": "auto",  # autodetección global por defecto
                "fixed_language_code": "es",
                "model_name": "small",
                "model_compute_type": "auto",
                "task_mode": "transcribe",  # "transcribe" | "translate" | "both"
                "device_preference": "auto",  # auto = detectar GPU al arrancar y usarla si está disponible
                "vad_enabled": False,
                "open_output_folder_on_finish": True,
                "overwrite_existing_files": False,
                "subtitle_max_line_length": 42,
                "subtitle_max_lines_per_segment": 2,
            },
            "batch": {
                "recursive_scan": False,
                "include_audio": True,
                "include_video": True,
                "skip_existing_outputs": True,
            },
            "runtime": {
                "first_run_completed": False,
                "last_used_on": "",
                "last_hardware_profile": {
                    "backend": "unknown",
                    "cuda_device_count": 0,
                    "total_ram_gb": 0.0,
                },
            },
        }

    def _load_or_initialize(self) -> None:
        """Carga config.json o lo crea con valores por defecto si es necesario."""
        default = self._default_config()

        if not self._path.exists():
            self._data = default
            self.save()
            return

        try:
            raw = self._path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            if not isinstance(loaded, dict):
                raise ValueError("La configuración no es un objeto JSON.")
        except Exception:
            # Archivo corrupto: resetear a valores por defecto y guardar.
            self._data = default
            self.save()
            return

        # Mezclar valores existentes con los valores por defecto.
        self._data = self._merge_dicts(default, loaded)
        # Guardar para incluir posibles nuevas claves por defecto.
        self.save()

    @staticmethod
    def _merge_dicts(default: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
        """Combina un diccionario existente con otro de valores por defecto."""
        result: Dict[str, Any] = {}
        for key, default_value in default.items():
            if key in existing:
                existing_value = existing[key]
                if isinstance(default_value, dict) and isinstance(existing_value, dict):
                    result[key] = Config._merge_dicts(default_value, existing_value)
                else:
                    result[key] = existing_value
            else:
                result[key] = default_value
        # Preservar claves desconocidas del archivo existente.
        for key, value in existing.items():
            if key not in result:
                result[key] = value
        return result

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor de configuración usando notación de punto.

        Ejemplo: get("preferences.mode")
        """
        parts = key.split(".")
        current: Any = self._data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def set(self, key: str, value: Any) -> None:
        """Establece un valor de configuración usando notación de punto.

        Crea los diccionarios intermedios necesarios si no existen.
        """
        parts = key.split(".")
        current: Dict[str, Any] = self._data
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]  # type: ignore[assignment]
        current[parts[-1]] = value

    def save(self) -> None:
        """Escribe la configuración actual en disco."""
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def reset(self) -> None:
        """Restablece la configuración a los valores por defecto y guarda."""
        self._data = self._default_config()
        self.save()


