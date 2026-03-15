"""Workers de procesamiento basados en QThread para Subtitulos Whisper.

Responsabilidad: ejecutar tareas de transcripción y exportación en
hilos separados, emitiendo señales de progreso, error y cancelación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

from PySide6.QtCore import QObject, QThread, Signal

LOGGER = logging.getLogger(__name__)

from .batch import Batch, BatchItem, BatchItemStatus
from .transcriber import Transcriber, TranscriptionSegment
from .exporter import Exporter


@dataclass
class TranscriptionJob:
    """Representa un trabajo de transcripción a procesar por un worker.

    Responsabilidad: agrupar la ruta de entrada, opciones de modelo y
    parámetros de salida necesarios para un proceso de transcripción.
    """

    # Ruta del archivo a transcribir
    input_path: Path

    # Opciones pasadas directamente a Transcriber.transcribe()
    # Claves esperadas: language_mode, language_code, vad_enabled, mode
    transcription_options: Dict[str, Any] = field(default_factory=dict)

    # Formatos de salida deseados: cualquier combinación de "txt", "srt", "vtt"
    output_formats: List[str] = field(default_factory=lambda: ["srt"])

    # Modo de tarea: "transcribe" | "translate" | "both"
    task_mode: str = "transcribe"

    # Carpeta de salida; None = misma carpeta que el archivo de entrada
    output_dir: Optional[Path] = None

    # Límites de formato para subtítulos SRT/VTT
    max_line_chars: int = 42
    max_lines_per_segment: int = 2


class TranscriptionWorker(QThread):
    """Hilo de trabajo encargado de procesar uno o varios archivos.

    Responsabilidad: coordinar la ejecución de transcripciones en
    segundo plano, informando a la UI del progreso y permitiendo cancelar.

    Uso típico:
        worker = TranscriptionWorker(transcriber, exporter, batch, jobs)
        worker.progress_changed.connect(progress_bar.setValue)
        worker.file_started.connect(lambda p: status_label.setText(p.name))
        worker.file_finished.connect(on_file_done)
        worker.error_occurred.connect(on_error)
        worker.finished_all.connect(on_all_done)
        worker.start()
    """

    # Progreso global de 0 a 100
    progress_changed = Signal(int)

    # Emitida justo antes de empezar a procesar un archivo
    file_started = Signal(Path)

    # Progreso del archivo actual de 0 a 100
    file_progress_changed = Signal(int)

    # Emitida cuando un archivo termina correctamente
    file_finished = Signal(Path)

    # Emitida cuando un archivo falla; incluye mensaje de error
    error_occurred = Signal(str)

    # Emitida al terminar todos los trabajos (o tras cancelación)
    finished_all = Signal()

    def __init__(
        self,
        transcriber: Transcriber,
        exporter: Exporter,
        batch: Batch,
        jobs: List[TranscriptionJob],
        parent: Optional[QObject] = None,
    ) -> None:
        """Inicializa el worker con sus dependencias y la cola de trabajos."""
        super().__init__(parent)
        self._transcriber = transcriber
        self._exporter = exporter
        self._batch = batch
        self._jobs = list(jobs)
        self._cancel_requested = False

    # ------------------------------------------------------------------
    # Control externo
    # ------------------------------------------------------------------

    def request_cancel(self) -> None:
        """Solicita la cancelación graciosa del procesamiento en curso.

        El worker terminará el archivo actual antes de detenerse.
        """
        self._cancel_requested = True

    # ------------------------------------------------------------------
    # Hilo principal
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Método principal del hilo que ejecuta la cola de trabajos."""
        total = len(self._jobs)
        try:
            if total == 0:
                return

            for index, job in enumerate(self._jobs):
                if self._cancel_requested:
                    self._batch.set_status(job.input_path, BatchItemStatus.CANCELED)
                    break

                self._process_job(job, index, total)
        finally:
            # Asegurarse de que siempre se emite la señal al finalizar,
            # independientemente de errores o cancelaciones.
            self.finished_all.emit()

    # ------------------------------------------------------------------
    # Procesamiento de un job individual
    # ------------------------------------------------------------------

    def _process_job(self, job: TranscriptionJob, index: int, total: int) -> None:
        """Transcribe y exporta un único archivo, actualizando el batch."""
        path = job.input_path
        task_mode = job.task_mode  # "transcribe" | "translate" | "both"

        self.file_started.emit(path)
        self._batch.set_status(path, BatchItemStatus.IN_PROGRESS)
        self.file_progress_changed.emit(0)

        # Determinar qué pasadas hay que hacer.
        passes: List[tuple[str, str]] = []  # (task, lang_suffix)
        if task_mode == "translate":
            passes = [("translate", ".en")]
        elif task_mode == "both":
            passes = [("transcribe", ""), ("translate", ".en")]
        else:
            passes = [("transcribe", "")]

        try:
            all_export_ok = True
            n_passes = len(passes)

            for pass_idx, (task, lang_suffix) in enumerate(passes):
                if self._cancel_requested:
                    break

                # Escalar el progreso del archivo por pasada (0-100 dividido entre pasadas).
                base_pct = pass_idx * 100 // n_passes

                def _cb(pct: int, base: int = base_pct, n: int = n_passes) -> None:
                    self.file_progress_changed.emit(base + pct // n)

                options = {**job.transcription_options, "task": task}
                try:
                    result = self._transcriber.transcribe(path, options, progress_callback=_cb)
                except Exception as exc:
                    msg = f"Error transcribiendo '{path.name}' (tarea={task}): {exc}"
                    self._batch.set_status(path, BatchItemStatus.ERROR, error=msg)
                    self.error_occurred.emit(msg)
                    return

                raw_segments = result.get("segments", [])
                if not raw_segments and not result.get("detected_language"):
                    msg = f"'{path.name}' no produjo resultados (tarea={task})."
                    self._batch.set_status(path, BatchItemStatus.ERROR, error=msg)
                    self.error_occurred.emit(msg)
                    return

                segments: List[TranscriptionSegment] = []
                for s in raw_segments:
                    try:
                        segments.append(
                            TranscriptionSegment(
                                start=float(s["start"]),
                                end=float(s["end"]),
                                text=str(s["text"]),
                                language=str(s.get("language", "")),
                            )
                        )
                    except Exception:
                        continue

                if not self._export(job, path, segments, lang_suffix=lang_suffix):
                    all_export_ok = False

            if all_export_ok and not self._cancel_requested:
                self._batch.set_status(path, BatchItemStatus.COMPLETED)
                self.file_progress_changed.emit(100)
                self.file_finished.emit(path)
            elif not all_export_ok:
                msg = f"Error al exportar '{path.name}'."
                self._batch.set_status(path, BatchItemStatus.ERROR, error=msg)
                self.error_occurred.emit(msg)
        finally:
            self._emit_progress(index + 1, total)

    def _export(
        self,
        job: TranscriptionJob,
        path: Path,
        segments: List[TranscriptionSegment],
        lang_suffix: str = "",
    ) -> bool:
        """Exporta los segmentos en los formatos solicitados.

        lang_suffix: cadena insertada antes de la extensión final, p.ej. ".en"
        genera  video.en.srt  en lugar de  video.srt.
        Devuelve True si todos los formatos se exportaron correctamente.
        """
        all_ok = True
        out_dir = job.output_dir if job.output_dir is not None else path.parent
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            LOGGER.error("No se pudo crear el directorio de salida '%s': %s", out_dir, exc)
        for fmt in job.output_formats:
            # video.mp4 + lang_suffix=".en" + fmt="srt"  →  video.en.srt
            output_path = out_dir / (path.stem + lang_suffix + f".{fmt.lower()}")
            method = self._exporter.get_exporter(fmt)
            if method:
                ok = method(segments, output_path)
            else:
                LOGGER.error("Formato de exportación desconocido: %s", fmt)
                ok = False
            if not ok:
                all_ok = False
        return all_ok

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit_progress(self, done: int, total: int) -> None:
        """Emite el progreso como porcentaje de 0 a 100."""
        pct = int(done * 100 / total) if total > 0 else 100
        self.progress_changed.emit(pct)