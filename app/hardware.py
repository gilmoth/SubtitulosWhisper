"""Detección de capacidades de hardware para Subtitulos Whisper.

Responsabilidad: detectar disponibilidad de CUDA/CPU, características
de GPU y CPU, y ofrecer una recomendación de dispositivo para los
modelos de Faster-Whisper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any
import os
import platform


DeviceType = Literal["cuda", "cpu", "auto"]


def _safe_cpu_cores() -> int:
    """Devuelve el número de núcleos de CPU disponibles sin lanzar excepciones."""
    try:
        count = os.cpu_count()
        if isinstance(count, int) and count > 0:
            return count
    except Exception:
        # Ignorar cualquier error y devolver un valor seguro.
        pass
    return 1


@dataclass
class HardwareProfile:
    """Perfil simplificado del hardware detectado en el sistema."""

    backend: Literal["cuda", "cpu", "unknown"]
    cuda_device_count: int
    cpu_cores: int
    total_ram_gb: float


def _safe_total_ram_gb() -> float:
    """Devuelve la RAM total del sistema en GB sin lanzar excepciones."""
    # Intento opcional con psutil si está disponible.
    try:
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:
            psutil = None  # type: ignore[assignment]
        if psutil is not None:
            try:
                total = psutil.virtual_memory().total
                return round(total / (1024**3), 2)
            except Exception:
                pass
    except Exception:
        # Ignorar cualquier problema relacionado con psutil.
        pass

    # Windows: usar GlobalMemoryStatusEx vía ctypes.
    try:
        if platform.system().lower() == "windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return round(status.ullTotalPhys / (1024**3), 2)
    except Exception:
        # Cualquier problema con ctypes o la API de Windows se ignora.
        pass

    # POSIX genérico: usar sysconf si está disponible.
    try:
        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")  # tipo: ignore[arg-type]
            pages = os.sysconf("SC_PHYS_PAGES")  # tipo: ignore[arg-type]
            if isinstance(page_size, int) and isinstance(pages, int):
                return round((page_size * pages) / (1024**3), 2)
    except Exception:
        # Ignorar cualquier error y devolver valor seguro.
        pass

    return 0.0


def _detect_cuda() -> tuple[bool, int]:
    """Detecta disponibilidad de CUDA y el número de GPUs sin lanzar excepciones."""
    # Primer intento: usar torch si está disponible.
    try:
        try:
            import torch  # type: ignore[import-not-found]
        except Exception:
            torch = None  # type: ignore[assignment]

        if torch is not None:
            try:
                if bool(torch.cuda.is_available()):  # type: ignore[union-attr]
                    count = int(torch.cuda.device_count() or 0)  # type: ignore[union-attr]
                    if count > 0:
                        return True, count
            except Exception:
                # Si falla torch, pasamos a la siguiente estrategia.
                pass
    except Exception:
        # Cualquier fallo inesperado con torch se ignora.
        pass

    # Segundo intento: usar ctranslate2 (dependencia de Faster-Whisper) si existe.
    try:
        try:
            import ctranslate2  # type: ignore[import-not-found]
        except Exception:
            ctranslate2 = None  # type: ignore[assignment]

        if ctranslate2 is not None:
            try:
                count = int(ctranslate2.get_cuda_device_count())  # type: ignore[union-attr]
                if count > 0:
                    return True, count
            except Exception:
                pass
    except Exception:
        # Cualquier error con ctranslate2 se ignora.
        pass

    return False, 0


class HardwareDetector:
    """Detector de características de hardware.

    Responsabilidad: encapsular la lógica de detección de GPU/CPU,
    RAM y recomendación de dispositivo para su uso por otros módulos.
    """

    def __init__(self) -> None:
        """Inicializa el detector sin ejecutar operaciones pesadas."""
        self._profile: Optional[HardwareProfile] = None

    def _compute_profile(self) -> HardwareProfile:
        """Calcula el perfil de hardware de forma segura."""
        try:
            cuda_available, cuda_count = _detect_cuda()
            cpu_cores = _safe_cpu_cores()
            total_ram_gb = _safe_total_ram_gb()

            if cuda_available and cuda_count > 0:
                backend: Literal["cuda", "cpu", "unknown"] = "cuda"
            else:
                backend = "cpu"

            return HardwareProfile(
                backend=backend,
                cuda_device_count=cuda_count,
                cpu_cores=cpu_cores,
                total_ram_gb=total_ram_gb,
            )
        except Exception:
            # Nunca propagar excepciones: devolver un perfil seguro.
            return HardwareProfile(
                backend="unknown",
                cuda_device_count=0,
                cpu_cores=1,
                total_ram_gb=0.0,
            )

    def detect(self) -> HardwareProfile:
        """Realiza la detección de hardware y devuelve un perfil resumido."""
        if self._profile is None:
            self._profile = self._compute_profile()
        return self._profile

    def recommend_device(self, preferred: DeviceType = "auto") -> DeviceType:
        """Devuelve el dispositivo recomendado en función del perfil y preferencia."""
        try:
            profile = self.detect()

            # Si el usuario indica explícitamente un dispositivo válido, se respeta.
            if preferred in ("cuda", "cpu"):
                return preferred

            # Modo "auto": preferir CUDA cuando está disponible.
            if profile.backend == "cuda" and profile.cuda_device_count > 0:
                return "cuda"
            return "cpu"
        except Exception:
            # Ante cualquier problema, devolver una opción segura.
            return "cpu"

    def get_recommended_device(self) -> str:
        """Devuelve el dispositivo recomendado ('cuda' o 'cpu')."""
        device = self.recommend_device("auto")
        # Garantizar que solo devolvemos 'cuda' o 'cpu'.
        return "cuda" if device == "cuda" else "cpu"

    def get_hardware_profile(self) -> Dict[str, Any]:
        """Devuelve un diccionario resumen con la información de hardware."""
        try:
            profile = self.detect()
            recommended = self.get_recommended_device()
            cuda_available = profile.backend == "cuda" and profile.cuda_device_count > 0
            return {
                "cuda_available": cuda_available,
                "cuda_device_count": profile.cuda_device_count,
                "cpu_cores": profile.cpu_cores,
                "total_ram_gb": profile.total_ram_gb,
                "recommended_device": recommended,
            }
        except Exception:
            # En caso de fallo, devolver un perfil mínimo pero consistente.
            return {
                "cuda_available": False,
                "cuda_device_count": 0,
                "cpu_cores": 1,
                "total_ram_gb": 0.0,
                "recommended_device": "cpu",
            }

