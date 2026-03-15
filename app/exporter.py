"""Exportación de resultados de transcripción a distintos formatos.

Responsabilidad: transformar segmentos transcritos en archivos .txt,
.srt y .vtt, aplicando las reglas de formato necesarias.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List
import logging

from .transcriber import TranscriptionSegment

LOGGER = logging.getLogger(__name__)


def _format_srt_time(seconds: float) -> str:
    """Convierte segundos a formato de tiempo SRT: HH:MM:SS,mmm"""
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Convierte segundos a formato de tiempo WebVTT: HH:MM:SS.mmm"""
    return _format_srt_time(seconds).replace(",", ".")


class Exporter:
    """Exportador de resultados de transcripción.

    Responsabilidad: generar archivos de salida (.txt, .srt, .vtt)
    a partir de los segmentos producidos por el transcriptor.
    """

    def __init__(self) -> None:
        self._EXPORTERS = {
            "txt": self.export_txt,
            "srt": self.export_srt,
            "vtt": self.export_vtt,
        }

    def get_exporter(self, fmt: str):
        return self._EXPORTERS.get(fmt.lower())

    # ------------------------------------------------------------------
    # TXT
    # ------------------------------------------------------------------

    def export_txt(
        self,
        segments: Iterable[TranscriptionSegment],
        output_path: Path,
    ) -> bool:
        """Genera un archivo de texto plano con el contenido transcrito.

        Devuelve True si se escribió correctamente.
        """
        try:
            lines: List[str] = []
            for seg in segments:
                text = seg.text.strip()
                if text:
                    lines.append(text)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("\n".join(lines), encoding="utf-8")
            LOGGER.info("TXT exportado: %s", output_path)
            return True
        except Exception as exc:
            LOGGER.error("Error al exportar TXT '%s': %s", output_path, exc)
            return False

    # ------------------------------------------------------------------
    # SRT
    # ------------------------------------------------------------------

    def export_srt(
        self,
        segments: Iterable[TranscriptionSegment],
        output_path: Path,
    ) -> bool:
        """Genera un archivo de subtítulos en formato SRT.

        Formato:
            1
            00:00:00,000 --> 00:00:05,000
            Texto del segmento

        Devuelve True si se escribió correctamente.
        """
        try:
            blocks: List[str] = []
            index = 1
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                start = _format_srt_time(seg.start)
                end = _format_srt_time(seg.end)
                blocks.append(f"{index}\n{start} --> {end}\n{text}")
                index += 1

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
            LOGGER.info("SRT exportado: %s", output_path)
            return True
        except Exception as exc:
            LOGGER.error("Error al exportar SRT '%s': %s", output_path, exc)
            return False

    # ------------------------------------------------------------------
    # VTT
    # ------------------------------------------------------------------

    def export_vtt(
        self,
        segments: Iterable[TranscriptionSegment],
        output_path: Path,
    ) -> bool:
        """Genera un archivo de subtítulos en formato WebVTT.

        Formato:
            WEBVTT

            00:00:00.000 --> 00:00:05.000
            Texto del segmento

        Devuelve True si se escribió correctamente.
        """
        try:
            lines: List[str] = ["WEBVTT", ""]
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                start = _format_vtt_time(seg.start)
                end = _format_vtt_time(seg.end)
                lines.append(f"{start} --> {end}")
                lines.append(text)
                lines.append("")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("\n".join(lines), encoding="utf-8")
            LOGGER.info("VTT exportado: %s", output_path)
            return True
        except Exception as exc:
            LOGGER.error("Error al exportar VTT '%s': %s", output_path, exc)
            return False