"""Lógica de transcripción basada en Faster-Whisper.

Responsabilidad: encapsular el uso de Faster-Whisper para convertir
audio/vídeo en texto y segmentos temporales, independiente de la UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
import subprocess
import tempfile

from .model_manager import ModelManager


LOGGER = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """Representa un segmento transcrito con información temporal."""

    start: float
    end: float
    text: str
    language: str


class Transcriber:
    """Motor de transcripción Faster-Whisper.

    Responsabilidad: orquestar la carga del modelo Whisper, el
    preprocesado de audio/vídeo y la generación de segmentos
    transcritos listos para la exportación.
    """

    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        model_manager: ModelManager,
        ffmpeg_path: str,
    ) -> None:
        """Inicializa el transcriptor sin cargar todavía ningún modelo.

        Los parámetros definen el modelo a utilizar, el dispositivo
        de ejecución y las dependencias externas necesarias.
        """
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._model_manager = model_manager
        self._ffmpeg_path = ffmpeg_path
        self._model = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Gestión de modelo
    # ------------------------------------------------------------------
    def load_model(self) -> bool:
        """Carga el modelo en memoria usando Faster-Whisper si no está ya cargado.

        Devuelve True si el modelo queda cargado correctamente.
        Nunca lanza excepciones no controladas.
        """
        if self._model is not None:
            return True

        try:
            model_path = self._model_manager.ensure_model(self._model_name)
            if model_path is None:
                LOGGER.error("No se pudo asegurar el modelo '%s'.", self._model_name)
                return False

            try:
                from faster_whisper import WhisperModel  # type: ignore[import-not-found]
            except Exception as exc:  # ImportError u otros
                LOGGER.error("No se pudo importar faster_whisper.WhisperModel: %s", exc)
                return False

            device = self._device if self._device in ("cuda", "cpu", "auto") else "auto"
            if device in ("auto", "cuda"):
                # Verificar CUDA usando ctranslate2 (dependencia real de faster-whisper).
                cuda_ok = False
                try:
                    import ctranslate2  # type: ignore[import-not-found]
                    cuda_ok = ctranslate2.get_cuda_device_count() > 0
                except Exception:
                    pass

                if cuda_ok:
                    device = "cuda"
                else:
                    if device == "cuda":
                        LOGGER.warning("CUDA seleccionado pero no disponible. Usando CPU.")
                    device = "cpu"

            if self._compute_type == "auto":
                compute_type = "float16" if device == "cuda" else "int8"
            else:
                compute_type = self._compute_type

            LOGGER.info(
                "Cargando modelo '%s' desde '%s' en device='%s' compute_type='%s'",
                self._model_name,
                model_path,
                device,
                compute_type,
            )

            try:
                self._loaded_device = device
                self._model = WhisperModel(
                    str(model_path),
                    device=device,
                    compute_type=compute_type,
                )
            except Exception as exc:
                LOGGER.error("Error al inicializar WhisperModel: %s", exc)
                self._model = None  # type: ignore[assignment]
                return False

            return True
        except Exception as exc:
            LOGGER.error("Error inesperado al cargar el modelo: %s", exc)
            self._model = None  # type: ignore[assignment]
            return False

    def unload_model(self) -> None:
        """Libera el modelo de memoria.

        Deja que el recolector de basura libere los recursos.
        """
        try:
            self._model = None  # type: ignore[assignment]
            import gc
            gc.collect()

            if getattr(self, "_loaded_device", None) == "cuda":
                try:
                    import torch  # type: ignore[import-not-found]
                    if hasattr(torch, "cuda") and torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
        except Exception as exc:
            LOGGER.error("Error al descargar el modelo de memoria: %s", exc)

    # ------------------------------------------------------------------
    # Preprocesado de audio / vídeo
    # ------------------------------------------------------------------
    def _convert_to_wav_mono_16k(self, input_path: Path, tmp_dir: Path) -> Optional[Path]:
        """Convierte el archivo de entrada a WAV mono 16k usando ffmpeg.

        Si la conversión falla o no hay ffmpeg disponible, devuelve None.
        Nunca lanza excepciones no controladas.
        """
        try:
            if not self._ffmpeg_path:
                return None

            ffmpeg = Path(self._ffmpeg_path)
            if not ffmpeg.is_file():
                LOGGER.warning("Ruta de ffmpeg no válida: %s", ffmpeg)
                return None

            output_path = tmp_dir / "input_16k_mono.wav"

            cmd = [
                str(ffmpeg),
                "-y",
                "-i",
                str(input_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(output_path),
            ]

            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600,
            )

            if proc.returncode != 0:
                LOGGER.error(
                    "ffmpeg falló al convertir '%s': %s", input_path, proc.stderr
                )
                return None

            if not output_path.is_file():
                LOGGER.error(
                    "La conversión con ffmpeg no generó el archivo esperado: %s",
                    output_path,
                )
                return None

            return output_path
        except Exception as exc:
            LOGGER.error("Error al convertir archivo con ffmpeg: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Transcripción
    # ------------------------------------------------------------------
    def _empty_result(self) -> Dict[str, Any]:
        """Devuelve una estructura de resultado vacía y segura."""
        return {
            "segments": [],
            "detected_language": "",
            "duration": 0.0,
        }

    def transcribe(self, file_path: Any, options: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """Transcribe un archivo de audio o vídeo y devuelve un diccionario de resultados.

        options debe contener:
            - language_mode: "auto", "single", "multi"
            - language_code: string (solo si language_mode == "single")
            - vad_enabled: bool
            - mode: "transcribe", "subtitle", "both" (informativo para esta capa)

        Nunca lanza excepciones no controladas.
        """
        result = self._empty_result()

        try:
            path = Path(file_path)
        except Exception as exc:
            LOGGER.error("Ruta de archivo no válida '%s': %s", file_path, exc)
            return result

        if not path.is_file():
            LOGGER.error("El archivo a transcribir no existe: %s", path)
            return result

        if "device" in options:
            self._device = options["device"]

        if not self.load_model():
            LOGGER.error("No se pudo cargar el modelo para la transcripción.")
            return result

        # Preparar opciones de lenguaje y VAD.
        language_mode = str(options.get("language_mode", "auto") or "auto")
        language_code = str(options.get("language_code", "") or "")
        vad_enabled = bool(options.get("vad_enabled", False))

        task = str(options.get("task", "transcribe") or "transcribe")
        if task not in ("transcribe", "translate"):
            task = "transcribe"

        language_arg: Optional[str]
        if language_mode == "single" and language_code:
            language_arg = language_code
        else:
            language_arg = None

        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except Exception as exc:
            LOGGER.error("No se pudo importar faster_whisper en transcribe: %s", exc)
            return result

        if self._model is None or not isinstance(self._model, WhisperModel):  # type: ignore[arg-type]
            LOGGER.error("El modelo Whisper no está inicializado correctamente.")
            return result

        try:
            with tempfile.TemporaryDirectory() as tmpdir_str:
                tmpdir = Path(tmpdir_str)

                converted = self._convert_to_wav_mono_16k(path, tmpdir)
                audio_source = str(converted if converted is not None else path)

                segments_iter, info = self._model.transcribe(  # type: ignore[call-arg]
                    audio_source,
                    language=language_arg,
                    task=task,
                    vad_filter=vad_enabled,
                )

                segments: List[Dict[str, Any]] = []
                default_lang = ""
                try:
                    default_lang = str(getattr(info, "language", "") or "")
                except Exception:
                    default_lang = ""

                try:
                    file_duration = float(getattr(info, "duration", 0.0))
                except Exception:
                    file_duration = 0.0

                for s in segments_iter:
                    if progress_callback and file_duration > 0:
                        try:
                            pct = min(99, int(float(getattr(s, "end", 0.0)) / file_duration * 100))
                            progress_callback(pct)
                        except Exception:
                            pass
                    try:
                        start = float(getattr(s, "start", 0.0))
                        end = float(getattr(s, "end", 0.0))
                        text = str(getattr(s, "text", ""))
                    except Exception:
                        # Si algún segmento es problemático, se omite.
                        continue

                    if language_mode == "single" and language_code:
                        seg_lang = language_code
                    else:
                        # Modo auto/multi: no forzar idioma, usar el detectado
                        # globalmente cuando esté disponible.
                        seg_lang = default_lang

                    segments.append(
                        {
                            "start": start,
                            "end": end,
                            "text": text,
                            "language": seg_lang,
                        }
                    )

                detected_language = default_lang
                try:
                    duration = float(getattr(info, "duration", 0.0))
                except Exception:
                    duration = 0.0

                if not segments:
                    LOGGER.warning(
                        "Transcripción sin segmentos. info.language='%s', info.duration=%.2f",
                        default_lang,
                        duration,
                    )

                result["segments"] = segments
                result["detected_language"] = detected_language
                result["duration"] = duration

        except Exception as exc:
            LOGGER.error("Error durante la transcripción: %s", exc)
            return result

        return result

