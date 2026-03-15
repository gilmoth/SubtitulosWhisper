"""Gestión de lotes (batch) de archivos para transcripción.

Responsabilidad: organizar colecciones de archivos de audio/vídeo,
su estado de procesamiento y las opciones aplicadas a cada uno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional
import logging

LOGGER = logging.getLogger(__name__)

# Extensiones de audio/vídeo soportadas
SUPPORTED_EXTENSIONS = {
    ".wav", ".mp3", ".mp4", ".m4a", ".flac", ".ogg",
    ".mkv", ".avi", ".mov", ".webm", ".wma", ".aac",
}


class BatchItemStatus(str, Enum):
    """Estados posibles de un elemento dentro de un batch."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELED = "canceled"
    SKIPPED = "skipped"


@dataclass
class BatchItem:
    """Elemento individual de un batch de procesamiento."""

    input_path: Path
    status: BatchItemStatus = BatchItemStatus.PENDING
    error_message: Optional[str] = None


@dataclass
class Batch:
    """Colección de elementos a procesar en modo batch.

    Responsabilidad: añadir, listar y actualizar el estado de
    múltiples archivos participantes en un procesamiento en lote.
    """

    items: List[BatchItem] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Añadir archivos
    # ------------------------------------------------------------------

    def add_file(self, path: Path) -> bool:
        """Añade un archivo individual al batch si tiene extensión soportada.

        Devuelve True si se añadió, False si se ignoró por extensión inválida
        o porque ya estaba en el batch.
        """
        path = path.resolve()

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            LOGGER.debug("Extensión no soportada, ignorado: %s", path)
            return False

        # Evitar duplicados
        if any(item.input_path == path for item in self.items):
            LOGGER.debug("Archivo ya en el batch, ignorado: %s", path)
            return False

        self.items.append(BatchItem(input_path=path))
        return True

    def add_folder(self, folder: Path, output_formats: Optional[List[str]] = None) -> int:
        """Escanea una carpeta y añade todos los archivos soportados.

        Omite automáticamente aquellos que ya tienen un archivo de salida
        con los sufijos indicados junto al archivo de audio (skip si ya existen todos).

        Devuelve el número de archivos añadidos.
        """
        if output_formats is None:
            output_formats = ["srt"]

        folder = folder.resolve()
        if not folder.is_dir():
            LOGGER.error("La ruta no es una carpeta válida: %s", folder)
            return 0

        added = 0
        for file in sorted(folder.iterdir()):
            if not file.is_file():
                continue
            if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            # Skip: si ya existen todos los archivos de salida esperados junto al audio
            all_exist = True
            for fmt in output_formats:
                output_path = file.with_suffix(f".{fmt.lower()}")
                if not output_path.exists():
                    all_exist = False
                    break

            if all_exist:
                LOGGER.info("Ya transcrito, saltando: %s", file.name)
                skipped_item = BatchItem(
                    input_path=file.resolve(),
                    status=BatchItemStatus.SKIPPED,
                )
                self.items.append(skipped_item)
                continue

            if self.add_file(file):
                added += 1

        LOGGER.info(
            "Carpeta '%s': %d archivos añadidos, %d saltados.",
            folder,
            added,
            self.count_by_status(BatchItemStatus.SKIPPED),
        )
        return added

    # ------------------------------------------------------------------
    # Actualización de estado
    # ------------------------------------------------------------------

    def set_status(self, path: Path, status: BatchItemStatus, error: Optional[str] = None) -> None:
        """Actualiza el estado de un item por su ruta."""
        path = path.resolve()
        for item in self.items:
            if item.input_path == path:
                item.status = status
                if error is not None:
                    item.error_message = error
                return
        LOGGER.warning("set_status: ruta no encontrada en el batch: %s", path)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def pending_items(self) -> List[BatchItem]:
        """Devuelve los items pendientes de procesar."""
        return [i for i in self.items if i.status == BatchItemStatus.PENDING]

    def count_by_status(self, status: BatchItemStatus) -> int:
        """Cuenta cuántos items tienen un estado concreto."""
        return sum(1 for i in self.items if i.status == status)

    def summary(self) -> str:
        """Devuelve un resumen legible del estado del batch."""
        total = len(self.items)
        pending = self.count_by_status(BatchItemStatus.PENDING)
        completed = self.count_by_status(BatchItemStatus.COMPLETED)
        skipped = self.count_by_status(BatchItemStatus.SKIPPED)
        errors = self.count_by_status(BatchItemStatus.ERROR)
        return (
            f"Total: {total} | Pendientes: {pending} | "
            f"Completados: {completed} | Saltados: {skipped} | Errores: {errors}"
        )