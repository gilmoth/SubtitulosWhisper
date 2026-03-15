"""Gestor de modelos Whisper para Subtitulos Whisper.

Responsabilidad: verificar, descargar y gestionar los modelos de
Faster-Whisper almacenados en el directorio de modelos de usuario.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
import logging

from .paths import get_models_dir


_LOGGER = logging.getLogger(__name__)

AVAILABLE_MODELS: List[str] = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
]

# Metadatos descriptivos de cada modelo para mostrar en la UI.
# speed y quality: 1 (mínimo) – 5 (máximo).
MODEL_METADATA: Dict[str, Any] = {
    # rtf_cpu / rtf_gpu: segundos de procesamiento por segundo de audio (estimación).
    # Valores menores = más rápido. Dependen del hardware; son orientativos.
    "tiny": {
        "size_label": "~75 MB",
        "speed": 5,
        "quality": 2,
        "vram_gb": 1,
        "rtf_cpu": 0.12,
        "rtf_gpu": 0.02,
        "desc": "El más ligero y rápido. Útil para pruebas o hardware muy limitado. Precisión básica.",
    },
    "base": {
        "size_label": "~145 MB",
        "speed": 4,
        "quality": 3,
        "vram_gb": 1,
        "rtf_cpu": 0.25,
        "rtf_gpu": 0.03,
        "desc": "Rápido con calidad aceptable. Buena opción cuando la velocidad importa más que la precisión.",
    },
    "small": {
        "size_label": "~465 MB",
        "speed": 3,
        "quality": 4,
        "vram_gb": 2,
        "rtf_cpu": 0.7,
        "rtf_gpu": 0.05,
        "desc": "Recomendado para uso general. Equilibrio entre velocidad y calidad. Buen soporte multiidioma.",
    },
    "medium": {
        "size_label": "~1.5 GB",
        "speed": 2,
        "quality": 5,
        "vram_gb": 5,
        "rtf_cpu": 2.0,
        "rtf_gpu": 0.15,
        "desc": "Alta precisión. Ideal para contenido con vocabulario técnico, acentos o audio de baja calidad.",
    },
    "large-v2": {
        "size_label": "~3 GB",
        "speed": 1,
        "quality": 5,
        "vram_gb": 10,
        "rtf_cpu": 4.0,
        "rtf_gpu": 0.3,
        "desc": "Máxima precisión. Requiere GPU con ~10 GB VRAM. Referencia de calidad en Whisper.",
    },
    "large-v3": {
        "size_label": "~3 GB",
        "speed": 1,
        "quality": 5,
        "vram_gb": 10,
        "rtf_cpu": 4.0,
        "rtf_gpu": 0.3,
        "desc": "Última versión large. Mejor precisión en idiomas de bajos recursos y casos difíciles.",
    },
}


@dataclass
class ModelInfo:
    """Información básica sobre un modelo Whisper disponible."""

    name: str
    size_mb: float
    path: Optional[Path]
    downloaded: bool


ProgressCallback = Callable[[float, str], None]


def _safe_dir_size_mb(path: Path) -> float:
    """Calcula el tamaño aproximado de un directorio en MB sin lanzar excepciones."""
    try:
        total = 0
        if not path.exists():
            return 0.0
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except Exception:
                # Ignorar archivos problemáticos.
                continue
        return round(total / (1024**2), 2)
    except Exception:
        return 0.0


class ModelManager:
    """Gestor de modelos Whisper.

    Responsabilidad: listar, verificar y descargar modelos Whisper,
    proporcionando rutas listas para el inicializado de Faster-Whisper.
    """

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        """Inicializa el gestor de modelos sin cargar modelos en memoria."""
        self._models_dir: Path = models_dir if models_dir is not None else get_models_dir()

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    def _is_supported_model(self, model_name: str) -> bool:
        """Indica si el modelo solicitado forma parte de la lista soportada."""
        return model_name in AVAILABLE_MODELS

    def _get_model_dir(self, model_name: str) -> Path:
        """Devuelve el directorio asociado a un modelo dentro del directorio base."""
        return self._models_dir / model_name

    # ------------------------------------------------------------------
    # API pública de consulta
    # ------------------------------------------------------------------
    def is_downloaded(self, model_name: str) -> bool:
        """Comprueba si el modelo ya está descargado y parece válido."""
        if not self._is_supported_model(model_name):
            return False

        try:
            model_dir = self._get_model_dir(model_name)
            model_file = model_dir / "model.bin"
            config_file = model_dir / "config.json"
            return model_dir.is_dir() and model_file.is_file() and config_file.is_file()
        except Exception as exc:
            _LOGGER.error("Error comprobando modelo '%s': %s", model_name, exc)
            return False

    def get_model_path(self, model_name: str) -> Optional[Path]:
        """Devuelve la ruta al directorio del modelo o None si no está disponible."""
        if not self.is_downloaded(model_name):
            return None
        try:
            return self._get_model_dir(model_name)
        except Exception as exc:
            _LOGGER.error("Error obteniendo ruta del modelo '%s': %s", model_name, exc)
            return None

    def get_downloaded_models(self) -> List[str]:
        """Devuelve una lista con los nombres de los modelos ya descargados."""
        result: List[str] = []
        for name in AVAILABLE_MODELS:
            if self.is_downloaded(name):
                result.append(name)
        return result

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Devuelve información básica sobre un modelo concreto."""
        downloaded = self.is_downloaded(model_name)
        path = self.get_model_path(model_name)
        size_mb = _safe_dir_size_mb(path) if path else 0.0
        return {
            "name": model_name,
            "downloaded": downloaded,
            "path": str(path) if path is not None else None,
            "size_mb": size_mb,
        }

    # ------------------------------------------------------------------
    # Descarga y aseguramiento
    # ------------------------------------------------------------------
    def download_model(
        self,
        model_name: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Optional[Path]:
        """Descarga el modelo indicado usando faster-whisper.

        El callback de progreso recibe (porcentaje: float, mensaje: str).
        """
        if not self._is_supported_model(model_name):
            _LOGGER.error("Modelo no soportado: '%s'", model_name)
            if progress_callback:
                try:
                    progress_callback(0.0, f"Modelo no soportado: {model_name}")
                except Exception:
                    pass
            return None

        try:
            try:
                from faster_whisper import download_model as fw_download_model  # type: ignore[import-not-found]
            except Exception as exc:
                _LOGGER.error("No se pudo importar faster_whisper.download_model: %s", exc)
                if progress_callback:
                    try:
                        progress_callback(0.0, "faster-whisper no está disponible")
                    except Exception:
                        pass
                return None

            dest_dir = self._get_model_dir(model_name)
            dest_dir.mkdir(parents=True, exist_ok=True)

            if progress_callback:
                try:
                    progress_callback(0.0, f"Descargando modelo '{model_name}'...")
                except Exception:
                    pass

            # La función de faster-whisper devuelve la ruta al modelo descargado.
            path_str = fw_download_model(model_name, output_dir=str(dest_dir))
            downloaded_path = Path(path_str)

            # Validar que el modelo descargado es utilizable.
            if not self.is_downloaded(model_name):
                _LOGGER.error(
                    "Modelo '%s' descargado pero la validación local ha fallado.",
                    model_name,
                )
                if progress_callback:
                    try:
                        progress_callback(
                            0.0,
                            f"Error al validar el modelo descargado '{model_name}'",
                        )
                    except Exception:
                        pass
                # Aun así devolvemos la ruta que reporta faster-whisper por si es utilizable.
                return downloaded_path

            if progress_callback:
                try:
                    progress_callback(100.0, f"Modelo '{model_name}' descargado.")
                except Exception:
                    pass

            return self.get_model_path(model_name)
        except Exception as exc:
            _LOGGER.error("Error al descargar el modelo '%s': %s", model_name, exc)
            if progress_callback:
                try:
                    progress_callback(0.0, f"Error al descargar el modelo '{model_name}'")
                except Exception:
                    pass
            return None

    def ensure_model(
        self,
        model_name: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Optional[Path]:
        """Garantiza que el modelo solicitado está descargado y devuelve su ruta."""
        try:
            if self.is_downloaded(model_name):
                if progress_callback:
                    try:
                        progress_callback(
                            100.0, f"Modelo '{model_name}' ya está disponible localmente."
                        )
                    except Exception:
                        pass
                return self.get_model_path(model_name)

            return self.download_model(model_name, progress_callback=progress_callback)
        except Exception as exc:
            _LOGGER.error("Error en ensure_model para '%s': %s", model_name, exc)
            if progress_callback:
                try:
                    progress_callback(0.0, f"Error al asegurar el modelo '{model_name}'")
                except Exception:
                    pass
            return None


