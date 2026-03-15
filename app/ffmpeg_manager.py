"""Gestor de FFMPEG para Subtitulos Whisper.

Responsabilidad: localizar, verificar y descargar automáticamente
ffmpeg.exe en sistemas Windows cuando no esté disponible en el PATH
ni en la carpeta de herramientas de la aplicación.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
import logging
import shutil
import subprocess
import sys
import tempfile
import zipfile

import requests

from .config import Config
from .paths import get_ffmpeg_dir


ProgressCallback = Callable[[int, int], None]

_LOGGER = logging.getLogger(__name__)


def _win_startupinfo() -> "subprocess.STARTUPINFO | None":
    """Devuelve un STARTUPINFO que oculta la ventana de consola en Windows."""
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si

FFMPEG_DOWNLOAD_URL = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)


class FFmpegManager:
    """Gestor de instalación y verificación de FFMPEG.

    Responsabilidad: asegurar que ffmpeg está disponible y operativo,
    manejando la descarga y actualización de su ubicación configurada.
    """

    def __init__(self) -> None:
        """Inicializa el gestor de FFMPEG sin ejecutar lógica pesada."""
        self._config = Config()
        self._cached_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    def _get_config_ffmpeg_path(self) -> Optional[Path]:
        """Obtiene la ruta de ffmpeg almacenada en la configuración, si es válida."""
        try:
            value = self._config.get("paths.ffmpeg_path", "")
            if not value:
                return None
            path = Path(value)
            if path.is_file():
                return path
        except Exception as exc:
            _LOGGER.warning("Error leyendo paths.ffmpeg_path en config: %s", exc)
        return None

    @staticmethod
    def get_audio_duration(file_path: Path, ffmpeg_path: Path) -> Optional[float]:
        """Devuelve la duración en segundos de un archivo usando ffprobe.

        Busca ffprobe.exe junto a ffmpeg.exe o en el PATH del sistema.
        Devuelve None si no puede determinarse la duración.
        """
        try:
            # ffprobe suele estar junto a ffmpeg.
            ffprobe = ffmpeg_path.parent / "ffprobe.exe"
            if not ffprobe.is_file():
                found = shutil.which("ffprobe")
                if not found:
                    return None
                ffprobe = Path(found)

            proc = subprocess.run(
                [
                    str(ffprobe), "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(file_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                startupinfo=_win_startupinfo(),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return float(proc.stdout.strip())
        except Exception as exc:
            _LOGGER.debug("No se pudo obtener duración de '%s': %s", file_path, exc)
        return None

    @staticmethod
    def _find_ffmpeg_in_path() -> Optional[Path]:
        """Busca ffmpeg en el PATH del sistema y devuelve su ruta si existe."""
        exe_name = "ffmpeg.exe"
        found = shutil.which(exe_name)
        if not found:
            # Como fallback, probar sin extensión (posibles entornos no Windows).
            found = shutil.which("ffmpeg")
        return Path(found) if found else None

    @staticmethod
    def _get_appdata_ffmpeg_executable() -> Path:
        """Devuelve la ruta esperada de ffmpeg.exe en la carpeta de la aplicación."""
        ffmpeg_dir = get_ffmpeg_dir()
        return ffmpeg_dir / "ffmpeg.exe"

    @staticmethod
    def _verify_ffmpeg(path: Path) -> bool:
        """Comprueba que ffmpeg responde correctamente a 'ffmpeg -version'."""
        try:
            if not path.is_file():
                return False
            proc = subprocess.run(
                [str(path), "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                startupinfo=_win_startupinfo(),
            )
            return proc.returncode == 0
        except Exception as exc:
            _LOGGER.error("Error al verificar ffmpeg en '%s': %s", path, exc)
            return False

    def _update_config_path(self, path: Path) -> None:
        """Actualiza la ruta de ffmpeg en la configuración."""
        try:
            self._config.set("paths.ffmpeg_path", str(path))
            self._config.save()
        except Exception as exc:
            _LOGGER.error("No se pudo guardar paths.ffmpeg_path en config: %s", exc)

    def _download_and_install_ffmpeg(
        self,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Optional[Path]:
        """Descarga y despliega ffmpeg en la carpeta de la aplicación."""
        tmp_file: Optional[tempfile.NamedTemporaryFile] = None
        try:
            _LOGGER.info("Descargando FFMPEG desde %s", FFMPEG_DOWNLOAD_URL)
            with requests.get(FFMPEG_DOWNLOAD_URL, stream=True, timeout=30) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", "0") or "0")
                downloaded = 0

                tmp_file = tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False
                )
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    tmp_file.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        try:
                            progress_callback(downloaded, total)
                        except Exception:
                            # Nunca dejar que el callback rompa el proceso.
                            pass
                tmp_file.flush()

            zip_path = Path(tmp_file.name)
            dest_dir = get_ffmpeg_dir()
            dest_exe = dest_dir / "ffmpeg.exe"

            _LOGGER.info("Descomprimiendo FFMPEG en %s", dest_dir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                member_name = None
                for info in zf.infolist():
                    if info.filename.lower().endswith("ffmpeg.exe"):
                        member_name = info.filename
                        break

                if member_name is None:
                    _LOGGER.error(
                        "No se encontró ffmpeg.exe dentro del ZIP descargado."
                    )
                    return None

                with zf.open(member_name) as src, open(dest_exe, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            if self._verify_ffmpeg(dest_exe):
                self._update_config_path(dest_exe)
                return dest_exe

            _LOGGER.error(
                "ffmpeg.exe instalado en %s pero la verificación ha fallado.",
                dest_exe,
            )
            return None
        except Exception as exc:
            _LOGGER.error("Error durante la descarga o instalación de FFMPEG: %s", exc)
            return None
        finally:
            # Limpiar archivo temporal si existe.
            if tmp_file is not None:
                try:
                    Path(tmp_file.name).unlink(missing_ok=True)  # type: ignore[arg-type]
                except Exception:
                    # Error al borrar el archivo temporal: se ignora.
                    pass

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def get_ffmpeg_path(self) -> Optional[Path]:
        """Devuelve la ruta actual de ffmpeg.exe si está configurada y es válida.

        No intenta descargar ni buscar en el PATH del sistema.
        """
        try:
            # Usar ruta cacheada si existe y sigue siendo válida.
            if self._cached_path and self._verify_ffmpeg(self._cached_path):
                return self._cached_path

            path = self._get_config_ffmpeg_path()
            if path and self._verify_ffmpeg(path):
                self._cached_path = path
                return path

            # Comprobar si ya existe en la carpeta de appdata.
            appdata_exe = self._get_appdata_ffmpeg_executable()
            if appdata_exe.is_file() and self._verify_ffmpeg(appdata_exe):
                self._cached_path = appdata_exe
                return appdata_exe
        except Exception as exc:
            _LOGGER.error("Error al obtener la ruta configurada de FFMPEG: %s", exc)
        return None

    def ensure_ffmpeg(
        self,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Optional[Path]:
        """Garantiza que ffmpeg está disponible y devuelve su ruta.

        Orden de búsqueda:
        1. Ruta guardada en config.json.
        2. PATH del sistema.
        3. %APPDATA%\\SubtitulosWhisper\\ffmpeg\\ffmpeg.exe
        4. Descarga e instalación automática en la carpeta de la aplicación.

        Nunca lanza excepciones no controladas; en caso de fallo devuelve None.
        """
        # 1. Ruta en configuración / appdata ya instalada.
        path = self.get_ffmpeg_path()
        if path is not None:
            return path

        # 2. Buscar en PATH del sistema.
        try:
            path_in_path = self._find_ffmpeg_in_path()
            if path_in_path and self._verify_ffmpeg(path_in_path):
                self._cached_path = path_in_path
                # Opcionalmente, guardar en config para acelerar futuras ejecuciones.
                self._update_config_path(path_in_path)
                return path_in_path
        except Exception as exc:
            _LOGGER.error("Error al buscar ffmpeg en PATH: %s", exc)

        # 3. Comprobar de nuevo la ruta de appdata explícitamente.
        try:
            appdata_exe = self._get_appdata_ffmpeg_executable()
            if appdata_exe.is_file() and self._verify_ffmpeg(appdata_exe):
                self._cached_path = appdata_exe
                self._update_config_path(appdata_exe)
                return appdata_exe
        except Exception as exc:
            _LOGGER.error("Error al comprobar ffmpeg en appdata: %s", exc)

        # 4. Descargar e instalar.
        installed = self._download_and_install_ffmpeg(progress_callback)
        if installed and self._verify_ffmpeg(installed):
            self._cached_path = installed
            return installed

        _LOGGER.error("No se ha podido asegurar una instalación funcional de FFMPEG.")
        return None

