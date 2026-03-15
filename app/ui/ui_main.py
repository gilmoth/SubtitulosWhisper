"""Ventana principal de la aplicación Subtitulos Whisper.

Responsabilidad: ofrecer la interfaz gráfica principal basada en
PySide6 para gestionar archivos, configuraciones y progreso.
"""

from __future__ import annotations

import html as html_mod
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, Slot, QObject, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QProgressBar,
    QAbstractItemView,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QTextEdit,
    QSizePolicy,
    QFrame,
)
from .settings_dialog import SettingsDialog
import logging

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Estilos globales de la aplicación
# ---------------------------------------------------------------------------

_APP_STYLE = """
QWidget {
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QRadioButton::indicator {
    width: 12px;
    height: 12px;
    border-radius: 6px;
    border: 2px solid #aaa;
    background: white;
}
QRadioButton::indicator:checked {
    background-color: #08aaac;
    border: 2px solid #08aaac;
}
QCheckBox::indicator {
    width: 12px;
    height: 12px;
    border: 2px solid #aaa;
    background: white;
}
QCheckBox::indicator:checked {
    background-color: #08aaac;
    border: 2px solid #08aaac;
}
QProgressBar {
    max-height: 4px;
    min-height: 4px;
    border: none;
    background: #e0e0e0;
    border-radius: 2px;
}
QProgressBar::chunk {
    background: #08aaac;
    border-radius: 2px;
}
QStatusBar {
    background: #057779;
    color: white;
    font-size: 12px;
}
QStatusBar::item {
    border: none;
}
QStatusBar QLabel {
    color: white;
    background: transparent;
    padding: 2px 8px;
}
"""

# Estilos de badge por estado (texto del estado → stylesheet para QLabel)
_BADGE_STYLES: dict[str, str] = {
    "Completado":  "background:#eaf3de; color:#3b6d11; border-radius:4px; padding:2px 10px;",
    "En progreso": "background:#e6f5f5; color:#057779; border-radius:4px; padding:2px 10px;",
    "Pendiente":   "background:#f0f0f0; color:#666666; border-radius:4px; padding:2px 10px;",
    "Saltado":     "background:#faeeda; color:#854f0b; border-radius:4px; padding:2px 10px;",
    "Error":       "background:#fce8e8; color:#c0392b; border-radius:4px; padding:2px 10px;",
    "Cancelado":   "background:#f5f5f5; color:#888888; border-radius:4px; padding:2px 10px;",
}


# ---------------------------------------------------------------------------
# Handler de logging thread-safe para el panel de log de la UI
# ---------------------------------------------------------------------------

class _LogSignalEmitter(QObject):
    """Emite mensajes de log como señal Qt para uso seguro entre hilos."""
    new_log = Signal(str)


class _UILogHandler(logging.Handler):
    """Handler de logging que redirige mensajes al panel de log de la UI."""

    def __init__(self, emitter: _LogSignalEmitter) -> None:
        super().__init__()
        self._emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emitter.new_log.emit(self.format(record))
        except Exception:
            pass

from ..batch import Batch, BatchItemStatus
from ..config import Config
from ..exporter import Exporter
from ..ffmpeg_manager import FFmpegManager
from ..hardware import HardwareDetector
from ..model_manager import ModelManager, MODEL_METADATA
from ..worker import TranscriptionWorker, TranscriptionJob
from ..transcriber import Transcriber


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación.

    Responsabilidad: coordinar los widgets de la UI y conectar los
    eventos de usuario con los workers y servicios de la aplicación.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Inicializa la ventana principal y configura la interfaz."""
        super().__init__(parent)

        icon_path = Path(__file__).parent / "resources" / "icon.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._config = Config()
        self._batch = Batch()
        self._worker: Optional[TranscriptionWorker] = None
        self._path_to_row: Dict[Path, int] = {}
        self._file_durations: Dict[Path, float] = {}  # caché de duraciones en segundos

        self._setup_ui()
        self._restore_window_state()
        self._setup_log_handler()

    # ------------------------------------------------------------------
    # Configuración de UI
    # ------------------------------------------------------------------

    @staticmethod
    def _make_vsep(parent: QWidget) -> QFrame:
        """Crea un separador vertical fino."""
        sep = QFrame(parent)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedWidth(1)
        sep.setStyleSheet("color: #d0d0d0;")
        return sep

    def _setup_ui(self) -> None:
        """Crea y organiza los widgets principales."""
        self.setStyleSheet(_APP_STYLE)

        central = QWidget(self)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ----------------------------------------------------------------
        # Toolbar container (3 filas)
        # ----------------------------------------------------------------
        toolbar = QWidget(self)
        toolbar.setObjectName("toolbar")
        toolbar.setStyleSheet(
            "#toolbar { background: #f5f5f5; border-bottom: 1px solid #d0d0d0; }"
        )
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(0)

        # --- Fila 1: TAREA | radios | sep | FORMATOS | checkboxes | estimate | sep | ▶ Iniciar | ⚙ ---
        _row1_w = QWidget(toolbar)
        _row1_w.setMinimumHeight(42)
        row1 = QHBoxLayout(_row1_w)
        row1.setContentsMargins(14, 10, 14, 10)
        row1.setSpacing(10)

        lbl_tarea = QLabel("TAREA", toolbar)
        lbl_tarea.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")

        self._radio_transcribe = QRadioButton("Transcribir", toolbar)
        self._radio_translate = QRadioButton("Traducir al inglés", toolbar)
        self._radio_both = QRadioButton("Ambos", toolbar)
        self._radio_transcribe.setToolTip(
            "Genera los archivos en el idioma original del audio."
        )
        self._radio_translate.setToolTip(
            "Genera los archivos traducidos al inglés (sufijo .en, p.ej. video.en.srt)."
        )
        self._radio_both.setToolTip(
            "Genera dos juegos de archivos: idioma original y traducción al inglés."
        )
        self._radio_transcribe.setChecked(True)
        task_group = QButtonGroup(self)
        task_group.setExclusive(True)
        task_group.addButton(self._radio_transcribe)
        task_group.addButton(self._radio_translate)
        task_group.addButton(self._radio_both)

        lbl_fmt = QLabel("FORMATOS", toolbar)
        lbl_fmt.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        self._chk_txt = QCheckBox("TXT", toolbar)
        self._chk_srt = QCheckBox("SRT", toolbar)
        self._chk_vtt = QCheckBox("VTT", toolbar)

        self._estimate_label = QLabel(toolbar)
        self._estimate_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        self._estimate_label.setToolTip(
            "Estimación orientativa. El tiempo real depende del hardware."
        )

        self._start_cancel_button = QPushButton("▶  Iniciar", toolbar)
        self._start_cancel_button.setStyleSheet(
            "QPushButton { background: #08aaac; color: white; border-radius: 6px;"
            " padding: 4px 18px; font-weight: bold; border: none; }"
            "QPushButton:hover { background: #057779; }"
            "QPushButton:pressed { background: #046264; }"
            "QPushButton:disabled { background: #a0a0a0; color: #ddd; }"
        )

        self._btn_settings = QPushButton("⚙", toolbar)
        self._btn_settings.setFixedSize(32, 28)
        self._btn_settings.setToolTip("Configuración")
        self._btn_settings.setStyleSheet(
            "QPushButton { border: 1px solid #ccc; border-radius: 4px; background: white; }"
            "QPushButton:hover { background: #e8e8e8; }"
            "QPushButton:pressed { background: #d0d0d0; }"
        )

        row1.addWidget(lbl_tarea)
        row1.addWidget(self._radio_transcribe)
        row1.addWidget(self._radio_translate)
        row1.addWidget(self._radio_both)
        row1.addWidget(self._make_vsep(toolbar))
        row1.addWidget(lbl_fmt)
        row1.addWidget(self._chk_txt)
        row1.addWidget(self._chk_srt)
        row1.addWidget(self._chk_vtt)
        row1.addStretch(1)
        row1.addWidget(self._estimate_label)
        row1.addWidget(self._make_vsep(toolbar))
        row1.addWidget(self._start_cancel_button)
        row1.addWidget(self._btn_settings)

        # --- Fila 2: ENTRADA | archivo/carpeta radios | sep | path edit | Examinar ---
        _row2_w = QWidget(toolbar)
        _row2_w.setMinimumHeight(42)
        row2 = QHBoxLayout(_row2_w)
        row2.setContentsMargins(14, 10, 14, 10)
        row2.setSpacing(10)

        lbl_entrada = QLabel("ENTRADA", toolbar)
        lbl_entrada.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        self._radio_file = QRadioButton("Archivo", toolbar)
        self._radio_folder = QRadioButton("Carpeta (batch)", toolbar)
        self._radio_file.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self._radio_file)
        mode_group.addButton(self._radio_folder)

        self._folder_edit = QLineEdit(toolbar)
        self._folder_edit.setPlaceholderText("Selecciona un archivo o carpeta...")
        self._browse_button = QPushButton("Examinar...", toolbar)

        row2.addWidget(lbl_entrada)
        row2.addWidget(self._radio_file)
        row2.addWidget(self._radio_folder)
        row2.addWidget(self._make_vsep(toolbar))
        row2.addWidget(self._folder_edit, 1)
        row2.addWidget(self._browse_button)

        # --- Fila 3: SALIDA | Misma carpeta checkbox | sep | output path edit | Examinar ---
        _row3_w = QWidget(toolbar)
        _row3_w.setMinimumHeight(42)
        row3 = QHBoxLayout(_row3_w)
        row3.setContentsMargins(14, 10, 14, 10)
        row3.setSpacing(10)

        lbl_salida = QLabel("SALIDA", toolbar)
        lbl_salida.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        self._chk_output_same = QCheckBox("Misma carpeta", toolbar)
        self._chk_output_same.setChecked(True)
        self._chk_output_same.setToolTip(
            "Guardar los archivos generados junto al audio de entrada"
        )

        self._output_dir_edit = QLineEdit(toolbar)
        self._output_dir_edit.setPlaceholderText("Misma carpeta que el audio")
        self._output_dir_edit.setEnabled(False)
        self._btn_browse_output = QPushButton("Examinar...", toolbar)
        self._btn_browse_output.setEnabled(False)

        row3.addWidget(lbl_salida)
        row3.addWidget(self._chk_output_same)
        row3.addWidget(self._make_vsep(toolbar))
        row3.addWidget(self._output_dir_edit, 1)
        row3.addWidget(self._btn_browse_output)

        toolbar_layout.addWidget(_row1_w)
        toolbar_layout.addWidget(_row2_w)
        toolbar_layout.addWidget(_row3_w)

        # ----------------------------------------------------------------
        # Tabla de archivos (3 columnas: Archivo | Duración | Estado)
        # ----------------------------------------------------------------
        self._table = QTableWidget(self)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["ARCHIVO", "DURACIÓN", "ESTADO"])
        header = self._table.horizontalHeader()
        header.setStyleSheet(
            "QHeaderView::section {"
            "  font-size: 11px; font-weight: bold; color: #555;"
            "  background: #fafafa; border-bottom: 1px solid #ddd;"
            "  padding: 4px 6px;"
            "}"
        )
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(1, 90)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        # ----------------------------------------------------------------
        # Barras de progreso (4 px de alto)
        # ----------------------------------------------------------------
        progress_container = QWidget(self)
        progress_container.setStyleSheet("background: #f5f5f5;")
        progress_layout = QVBoxLayout(progress_container)
        progress_layout.setContentsMargins(10, 6, 10, 6)
        progress_layout.setSpacing(4)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        lbl_file = QLabel("Archivo", progress_container)
        lbl_file.setStyleSheet("font-size: 10px; color: #888;")
        lbl_file.setFixedWidth(50)
        self._file_progress_bar = QProgressBar(progress_container)
        self._file_progress_bar.setRange(0, 100)
        self._file_progress_bar.setValue(0)
        self._file_progress_bar.setTextVisible(False)
        file_row.addWidget(lbl_file)
        file_row.addWidget(self._file_progress_bar, 1)

        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)
        lbl_batch = QLabel("Lote", progress_container)
        lbl_batch.setStyleSheet("font-size: 10px; color: #888;")
        lbl_batch.setFixedWidth(50)
        self._progress_bar = QProgressBar(progress_container)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        batch_row.addWidget(lbl_batch)
        batch_row.addWidget(self._progress_bar, 1)

        progress_layout.addLayout(file_row)
        progress_layout.addLayout(batch_row)

        # ----------------------------------------------------------------
        # Panel de log desplegable
        # ----------------------------------------------------------------
        log_wrapper = QWidget(self)
        log_wrapper_layout = QVBoxLayout(log_wrapper)
        log_wrapper_layout.setContentsMargins(10, 2, 10, 4)
        log_wrapper_layout.setSpacing(0)

        log_toggle_row = QHBoxLayout()
        self._btn_toggle_log = QPushButton("▶  Log", log_wrapper)
        self._btn_toggle_log.setCheckable(True)
        self._btn_toggle_log.setChecked(False)
        self._btn_toggle_log.setFlat(True)
        self._btn_toggle_log.setStyleSheet("font-size: 11px; color: #666;")
        log_toggle_row.addWidget(self._btn_toggle_log)
        log_toggle_row.addStretch(1)

        self._log_panel = QTextEdit(log_wrapper)
        self._log_panel.setReadOnly(True)
        self._log_panel.document().setMaximumBlockCount(500)
        self._log_panel.setFixedHeight(160)
        self._log_panel.setVisible(False)
        mono_font = QFont("Consolas", 8)
        self._log_panel.setFont(mono_font)
        self._log_panel.setStyleSheet(
            "QTextEdit { background: #1e1e2e; color: #a6e3a1; border: none; }"
        )

        log_wrapper_layout.addLayout(log_toggle_row)
        log_wrapper_layout.addWidget(self._log_panel)

        # ----------------------------------------------------------------
        # Ensamblar layout principal
        # ----------------------------------------------------------------
        main_layout.addWidget(toolbar)
        main_layout.addWidget(self._table, 1)
        main_layout.addWidget(progress_container)
        main_layout.addWidget(log_wrapper)

        self.setCentralWidget(central)
        self.setWindowTitle("Subtitulos Whisper")

        # ----------------------------------------------------------------
        # Barra de estado (fondo azul, texto blanco)
        # ----------------------------------------------------------------
        self._status_left_label = QLabel(self)
        self._status_right_label = QLabel(self)
        sb = self.statusBar()
        sb.setStyleSheet(
            "QStatusBar { background: #057779; }"
            "QStatusBar::item { border: none; }"
        )
        self._btn_clear = QPushButton("🗑")
        self._btn_clear.setToolTip("Limpiar lista")
        self._btn_clear.setFixedSize(24, 24)
        self._btn_clear.setStyleSheet(
            "QPushButton { background: transparent; color: white;"
            " border: none; font-size: 14px; }"
            "QPushButton:hover { color: #ffcccc; }"
        )
        sb.addWidget(self._status_left_label, 1)
        sb.addPermanentWidget(self._status_right_label)
        sb.addPermanentWidget(self._btn_clear)
        self._btn_clear.clicked.connect(self._on_clear_clicked)

        # ----------------------------------------------------------------
        # Conexión de señales de UI
        # ----------------------------------------------------------------
        self._browse_button.clicked.connect(self._on_browse_clicked)
        self._start_cancel_button.clicked.connect(self._on_start_cancel_clicked)
        self._chk_output_same.toggled.connect(self._on_output_same_toggled)
        self._btn_browse_output.clicked.connect(self._on_browse_output_clicked)
        self._output_dir_edit.editingFinished.connect(self._on_output_dir_edited)

        self._chk_txt.stateChanged.connect(self._on_format_checkbox_changed)
        self._chk_srt.stateChanged.connect(self._on_format_checkbox_changed)
        self._chk_vtt.stateChanged.connect(self._on_format_checkbox_changed)

        self._radio_file.toggled.connect(self._on_input_mode_changed)
        self._radio_folder.toggled.connect(self._on_input_mode_changed)

        self._btn_settings.clicked.connect(self._on_open_settings)

        self._radio_transcribe.toggled.connect(self._on_task_changed)
        self._radio_translate.toggled.connect(self._on_task_changed)
        self._radio_both.toggled.connect(self._on_task_changed)

        self._btn_toggle_log.toggled.connect(self._on_toggle_log)

        # Restaurar desde configuración
        self._apply_mode_from_config()
        self._apply_input_mode_from_config()
        self._apply_startup_device()
        self._refresh_summary_label()
        self._apply_task_from_config()

        last_input = self._config.get("paths.last_input_path", "")
        if last_input:
            self._folder_edit.setText(last_input)

        self._apply_output_dir_from_config()

    def _restore_window_state(self) -> None:
        """Restaura el tamaño y estado de la ventana desde la configuración."""
        width = int(self._config.get("ui.window_width", 1200) or 1200)
        height = int(self._config.get("ui.window_height", 800) or 800)
        is_maximized = bool(self._config.get("ui.is_maximized", False))

        self.resize(width, height)
        if is_maximized:
            self.showMaximized()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Guarda el estado de la ventana al cerrarse."""
        is_maximized = self.isMaximized()
        if is_maximized:
            self._config.set("ui.is_maximized", True)
        else:
            self._config.set("ui.is_maximized", False)
            self._config.set("ui.window_width", self.width())
            self._config.set("ui.window_height", self.height())

        self._config.set("preferences.mode", self._get_mode_from_checkboxes())
        self._config.set("preferences.input_mode", self._get_input_mode())
        self._config.set("paths.output_dir", self._get_output_dir_str())

        self._config.save()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Helpers de formatos de salida
    # ------------------------------------------------------------------

    def _apply_mode_from_config(self) -> None:
        """Aplica el modo de salida almacenado en configuración a los checkboxes."""
        mode = str(self._config.get("preferences.mode", "both") or "both")

        txt = False
        srt = False
        vtt = False

        if mode == "txt":
            txt = True
        elif mode == "srt":
            srt = True
        elif mode == "vtt":
            vtt = True
        elif mode == "all":
            txt = srt = vtt = True
        else:
            txt = True
            srt = True

        for chk, value in (
            (self._chk_txt, txt),
            (self._chk_srt, srt),
            (self._chk_vtt, vtt),
        ):
            chk.blockSignals(True)
            chk.setChecked(value)
            chk.blockSignals(False)

        if not (self._chk_txt.isChecked() or self._chk_srt.isChecked() or self._chk_vtt.isChecked()):
            self._chk_srt.setChecked(True)

    def _get_mode_from_checkboxes(self) -> str:
        """Devuelve el modo a partir de los checkboxes actuales."""
        txt = self._chk_txt.isChecked()
        srt = self._chk_srt.isChecked()
        vtt = self._chk_vtt.isChecked()

        if txt and srt and vtt:
            return "all"
        if txt and srt and not vtt:
            return "both"
        if txt and not srt and not vtt:
            return "txt"
        if srt and not txt and not vtt:
            return "srt"
        if vtt and not txt and not srt:
            return "vtt"

        return "both"

    @Slot(int)
    def _on_format_checkbox_changed(self, _state: int) -> None:
        """Garantiza que al menos un formato permanezca seleccionado."""
        if not (self._chk_txt.isChecked() or self._chk_srt.isChecked() or self._chk_vtt.isChecked()):
            sender = self.sender()
            if isinstance(sender, QCheckBox):
                sender.blockSignals(True)
                sender.setChecked(True)
                sender.blockSignals(False)

    # ------------------------------------------------------------------
    # Helpers de modo de tarea (transcribir / traducir / ambos)
    # ------------------------------------------------------------------

    def _get_task_mode(self) -> str:
        """Devuelve el modo de tarea actual."""
        if self._radio_translate.isChecked():
            return "translate"
        if self._radio_both.isChecked():
            return "both"
        return "transcribe"

    def _apply_task_from_config(self) -> None:
        """Restaura el modo de tarea desde la configuración."""
        mode = str(self._config.get("preferences.task_mode", "transcribe") or "transcribe")
        self._radio_transcribe.blockSignals(True)
        self._radio_translate.blockSignals(True)
        self._radio_both.blockSignals(True)
        if mode == "translate":
            self._radio_translate.setChecked(True)
        elif mode == "both":
            self._radio_both.setChecked(True)
        else:
            self._radio_transcribe.setChecked(True)
        self._radio_transcribe.blockSignals(False)
        self._radio_translate.blockSignals(False)
        self._radio_both.blockSignals(False)

    @Slot()
    def _on_task_changed(self) -> None:
        """Guarda el modo de tarea al cambiar el radio."""
        if not self.sender() or not self.sender().isChecked():  # type: ignore[union-attr]
            return
        self._config.set("preferences.task_mode", self._get_task_mode())
        self._config.save()

    # ------------------------------------------------------------------
    # Helpers de modo de entrada (archivo/carpeta)
    # ------------------------------------------------------------------

    def _get_input_mode(self) -> str:
        """Devuelve el modo de entrada actual ('file' o 'folder')."""
        return "file" if self._radio_file.isChecked() else "folder"

    def _apply_input_mode_from_config(self) -> None:
        """Restaura el modo de entrada desde la configuración."""
        mode = str(self._config.get("preferences.input_mode", "file") or "file")
        if mode == "folder":
            self._radio_folder.setChecked(True)
            self._radio_file.setChecked(False)
        else:
            self._radio_file.setChecked(True)
            self._radio_folder.setChecked(False)

        self._update_browse_button_label()

    def _update_browse_button_label(self) -> None:
        """Actualiza el texto del botón Examinar según el modo de entrada."""
        if self._get_input_mode() == "file":
            self._browse_button.setText("Examinar archivo...")
        else:
            self._browse_button.setText("Examinar carpeta...")

    @Slot()
    def _on_input_mode_changed(self) -> None:
        """Actualiza UI y configuración cuando cambia el modo de entrada."""
        self._update_browse_button_label()
        self._config.set("preferences.input_mode", self._get_input_mode())
        self._config.save()

    # ------------------------------------------------------------------
    # Helpers de carpeta de salida
    # ------------------------------------------------------------------

    def _get_output_dir_str(self) -> str:
        """Devuelve la ruta de salida configurada, o '' si es la misma que la entrada."""
        if self._chk_output_same.isChecked():
            return ""
        return self._output_dir_edit.text().strip()

    def _get_output_dir(self) -> Optional[Path]:
        """Devuelve la carpeta de salida como Path, o None si es la misma que la entrada."""
        val = self._get_output_dir_str()
        return Path(val) if val else None

    def _apply_output_dir_from_config(self) -> None:
        """Restaura el estado de la carpeta de salida desde la configuración."""
        saved = str(self._config.get("paths.output_dir", "") or "")
        if saved:
            self._chk_output_same.setChecked(False)
            self._output_dir_edit.setText(saved)
            self._output_dir_edit.setEnabled(True)
            self._btn_browse_output.setEnabled(True)
        else:
            self._chk_output_same.setChecked(True)
            self._output_dir_edit.setText("")
            self._output_dir_edit.setEnabled(False)
            self._btn_browse_output.setEnabled(False)

    @Slot(bool)
    def _on_output_same_toggled(self, checked: bool) -> None:
        """Habilita o deshabilita los controles de carpeta de salida."""
        self._output_dir_edit.setEnabled(not checked)
        self._btn_browse_output.setEnabled(not checked)
        if checked:
            self._output_dir_edit.clear()
        self._config.set("paths.output_dir", self._get_output_dir_str())
        self._config.save()

    @Slot()
    def _on_browse_output_clicked(self) -> None:
        """Abre diálogo para seleccionar carpeta de salida."""
        current = self._output_dir_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de salida", current or ""
        )
        if folder:
            self._output_dir_edit.setText(folder)
            self._config.set("paths.output_dir", folder)
            self._config.save()

    @Slot()
    def _on_output_dir_edited(self) -> None:
        """Guarda la carpeta de salida editada manualmente."""
        self._config.set("paths.output_dir", self._get_output_dir_str())
        self._config.save()

    # ------------------------------------------------------------------
    # Panel de log
    # ------------------------------------------------------------------

    def _setup_log_handler(self) -> None:
        """Instala el handler de logging que redirige mensajes al panel de la UI."""
        self._log_emitter = _LogSignalEmitter(self)
        self._log_emitter.new_log.connect(self._on_new_log_message)

        handler = _UILogHandler(self._log_emitter)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"
        ))
        handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(handler)

    @Slot(bool)
    def _on_toggle_log(self, checked: bool) -> None:
        """Despliega u oculta el panel de log."""
        self._log_panel.setVisible(checked)
        self._btn_toggle_log.setText("▼  Log" if checked else "▶  Log")

    @Slot(str)
    def _on_new_log_message(self, message: str) -> None:
        """Añade un mensaje coloreado al panel de log."""
        msg_escaped = html_mod.escape(message)

        if "[ERROR]" in message or "[CRITICAL]" in message:
            color = "#f38ba8"
        elif "[WARNING]" in message:
            color = "#f9e2af"
        elif "[DEBUG]" in message:
            color = "#6c7086"
        elif "[INFO]" in message:
            color = "#89dceb"
        else:
            color = "#a6e3a1"

        self._log_panel.append(
            f'<span style="color:{color}; font-family:Consolas; font-size:8pt;">'
            f'{msg_escaped}</span>'
        )

    # ------------------------------------------------------------------
    # Helpers de configuración / resumen
    # ------------------------------------------------------------------

    def _current_device(self) -> str:
        """Devuelve el dispositivo activo leyendo desde la configuración."""
        return str(self._config.get("preferences.device_preference", "cpu") or "cpu")

    def _current_model(self) -> str:
        """Devuelve el nombre del modelo activo desde la configuración."""
        return str(self._config.get("preferences.model_name", "small") or "small")

    def _apply_startup_device(self) -> None:
        """Detecta CUDA silenciosamente al arrancar si la preferencia es 'auto'."""
        device_pref = str(self._config.get("preferences.device_preference", "auto") or "auto")
        if device_pref not in ("auto", "cuda"):
            return

        detector = HardwareDetector()
        profile = detector.detect()
        cuda_ok = profile.backend == "cuda" and profile.cuda_device_count > 0

        if cuda_ok:
            gpu_label = f"{profile.cuda_device_count} GPU(s) CUDA"
            try:
                import torch  # type: ignore[import-not-found]
                gpu_label = torch.cuda.get_device_name(0)
            except Exception:
                pass
            self._config.set("preferences.device_preference", "cuda")
            self._config.set("runtime.cuda_device_name", gpu_label)
            LOGGER.info("CUDA detectado al arrancar: %s", gpu_label)
        else:
            self._config.set("preferences.device_preference", "cpu")
            self._config.set("runtime.cuda_device_name", "")
            LOGGER.info("CUDA no disponible al arrancar, usando CPU.")
        self._config.save()

    def _refresh_summary_label(self) -> None:
        """Actualiza la barra de estado con modelo y dispositivo actuales."""
        model = self._current_model()
        device = self._current_device()
        gpu_name = str(self._config.get("runtime.cuda_device_name", "") or "")

        device_str = f"CUDA ({gpu_name})" if device == "cuda" and gpu_name else device.upper()
        dot_color = "#90ee90" if device == "cuda" else "#cccccc"

        self._status_left_label.setText(
            f'<span style="color:{dot_color};">●</span>'
            f'&nbsp;&nbsp;{device_str}&nbsp;&nbsp;·&nbsp;&nbsp;Modelo: {model}'
        )

    @Slot()
    def _on_open_settings(self) -> None:
        """Abre el diálogo de configuración."""
        dlg = SettingsDialog(self._config, parent=self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    @Slot()
    def _on_settings_changed(self) -> None:
        """Refresca la UI cuando cambia alguna configuración desde el diálogo."""
        self._refresh_summary_label()
        self._update_time_estimate()

    def _fetch_durations_for_batch(self) -> None:
        """Obtiene y cachea las duraciones de los archivos pendientes del batch."""
        ffmpeg_path: Optional[Path] = None
        try:
            ffmpeg_str = str(self._config.get("paths.ffmpeg_path", "") or "")
            if ffmpeg_str:
                p = Path(ffmpeg_str)
                if p.is_file():
                    ffmpeg_path = p
        except Exception:
            pass

        if ffmpeg_path is None:
            return

        for item in self._batch.items:
            path = item.input_path
            if path not in self._file_durations:
                dur = FFmpegManager.get_audio_duration(path, ffmpeg_path)
                if dur is not None:
                    self._file_durations[path] = dur

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Formatea segundos en una cadena legible."""
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        if m < 60:
            return f"{m}m {s:02d}s" if s else f"{m}m"
        h, m = divmod(m, 60)
        return f"{h}h {m:02d}m"

    def _update_time_estimate(self) -> None:
        """Calcula y muestra el tiempo estimado de transcripción."""
        if not self._batch.items:
            self._estimate_label.setText("")
            return

        total_audio_secs = sum(
            self._file_durations.get(item.input_path, 0.0)
            for item in self._batch.items
        )
        if total_audio_secs <= 0:
            self._estimate_label.setText("")
            return

        model_name = self._current_model()
        meta = MODEL_METADATA.get(model_name, {})
        device = self._current_device()
        rtf_key = "rtf_gpu" if device == "cuda" else "rtf_cpu"
        rtf = meta.get(rtf_key, 1.0)

        estimated_secs = total_audio_secs * rtf
        audio_fmt = self._format_duration(total_audio_secs)
        est_fmt = self._format_duration(estimated_secs)
        device_label = "GPU" if device == "cuda" else "CPU"

        self._estimate_label.setText(f"⏱ ~{est_fmt}  ({device_label}, {audio_fmt} de audio)")
        color = "#1a7f37" if estimated_secs < 120 else ("#b08000" if estimated_secs < 600 else "#c0392b")
        self._estimate_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")

    # ------------------------------------------------------------------
    # Helpers de batch y tabla
    # ------------------------------------------------------------------

    def _status_to_text(self, status: BatchItemStatus) -> str:
        """Convierte un estado interno en una etiqueta legible."""
        mapping = {
            BatchItemStatus.PENDING: "Pendiente",
            BatchItemStatus.IN_PROGRESS: "En progreso",
            BatchItemStatus.COMPLETED: "Completado",
            BatchItemStatus.ERROR: "Error",
            BatchItemStatus.CANCELED: "Cancelado",
            BatchItemStatus.SKIPPED: "Saltado",
        }
        return mapping.get(status, status.value)

    def _set_status_badge(self, row: int, status: BatchItemStatus) -> None:
        """Coloca un badge coloreado en la columna Estado de la fila indicada."""
        text = self._status_to_text(status)
        style = _BADGE_STYLES.get(
            text,
            "background:#f0f0f0; color:#666; border-radius:4px; padding:2px 10px;",
        )
        badge = QLabel(text)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(style)

        container = QWidget()
        cl = QHBoxLayout(container)
        cl.setContentsMargins(4, 2, 4, 2)
        cl.addWidget(badge)
        self._table.setCellWidget(row, 2, container)

    def _refresh_batch_table(self) -> None:
        """Refresca la tabla de archivos según el estado del batch."""
        self._table.setRowCount(len(self._batch.items))
        self._path_to_row.clear()

        for row, item in enumerate(self._batch.items):
            self._path_to_row[item.input_path] = row

            name_item = QTableWidgetItem(item.input_path.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, name_item)

            dur = self._file_durations.get(item.input_path)
            dur_text = self._format_duration(dur) if dur is not None else "—"
            dur_item = QTableWidgetItem(dur_text)
            dur_item.setTextAlignment(Qt.AlignCenter)
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 1, dur_item)

            self._set_status_badge(row, item.status)

    def _update_status_for_path(self, path: Path) -> None:
        """Actualiza la columna de estado para un archivo concreto."""
        path = path.resolve()
        row = self._path_to_row.get(path)
        if row is None:
            self._refresh_batch_table()
            return

        if row < 0 or row >= len(self._batch.items):
            return

        item = self._batch.items[row]
        self._set_status_badge(row, item.status)

    # ------------------------------------------------------------------
    # Slots de UI
    # ------------------------------------------------------------------

    @Slot()
    def _on_clear_clicked(self) -> None:
        """Limpia la tabla y resetea el batch si no hay worker en ejecución."""
        if self._worker is not None and self._worker.isRunning():
            return
        self._batch.items.clear()
        self._path_to_row.clear()
        self._file_durations.clear()
        self._table.setRowCount(0)
        self._progress_bar.setValue(0)
        self._file_progress_bar.setValue(0)
        self._estimate_label.setText("")
        if self._get_input_mode() == "folder":
            self._folder_edit.clear()

    @Slot()
    def _on_browse_clicked(self) -> None:
        """Abre un diálogo para seleccionar archivo o carpeta según el modo."""
        start_dir = self._folder_edit.text().strip() or self._config.get(
            "paths.last_input_path", ""
        )

        if self._get_input_mode() == "file":
            filters = (
                "Audio/Vídeo (*.wav *.mp3 *.mp4 *.m4a *.flac *.ogg "
                "*.mkv *.avi *.mov *.webm *.wma *.aac);;Todos los archivos (*.*)"
            )
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar archivo de entrada",
                start_dir or "",
                filters,
            )
            if not file_path:
                return

            self._folder_edit.setText(file_path)
            self._config.set("paths.last_input_path", str(Path(file_path).parent))
            self._config.save()

            self._load_file_into_batch(Path(file_path))
        else:
            folder = QFileDialog.getExistingDirectory(
                self,
                "Seleccionar carpeta de entrada",
                start_dir or "",
            )
            if not folder:
                return

            self._folder_edit.setText(folder)
            self._config.set("paths.last_input_path", folder)
            self._config.save()

            self._load_folder_into_batch(Path(folder))

    def _load_folder_into_batch(self, folder: Path, output_formats: Optional[list[str]] = None) -> None:
        """Carga los archivos de una carpeta en el batch y actualiza la tabla."""
        self._batch = Batch()
        added = self._batch.add_folder(folder, output_formats=output_formats)
        if added == 0 and not self._batch.items:
            QMessageBox.information(
                self,
                "Sin archivos",
                "No se encontraron archivos de audio o vídeo soportados en la carpeta.",
            )

        self._refresh_batch_table()
        self._progress_bar.setValue(0)
        self._fetch_durations_for_batch()
        self._update_time_estimate()

    def _load_file_into_batch(self, file_path: Path) -> None:
        """Carga un único archivo en el batch y actualiza la tabla."""
        self._batch = Batch()
        added = self._batch.add_file(file_path)
        if not added:
            QMessageBox.warning(
                self,
                "Archivo no válido",
                "El archivo seleccionado no tiene una extensión soportada "
                "o ya estaba en el lote.",
            )
            return

        self._refresh_batch_table()
        self._progress_bar.setValue(0)
        self._fetch_durations_for_batch()
        self._update_time_estimate()

    @Slot()
    def _on_start_cancel_clicked(self) -> None:
        """Inicia o cancela el procesamiento según el estado actual."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_cancel()
            self._start_cancel_button.setEnabled(False)
            return

        input_text = self._folder_edit.text().strip()
        if not input_text:
            if self._get_input_mode() == "file":
                QMessageBox.warning(
                    self, "Archivo no seleccionado", "Selecciona un archivo de entrada."
                )
            else:
                QMessageBox.warning(
                    self, "Carpeta no seleccionada", "Selecciona una carpeta de entrada."
                )
            return

        if self._get_input_mode() == "file":
            file_path = Path(input_text)
            if not file_path.is_file():
                QMessageBox.warning(
                    self,
                    "Archivo inválido",
                    "La ruta seleccionada no es un archivo válido.",
                )
                return

            if not self._batch.items or len(self._batch.items) != 1 or self._batch.items[0].input_path != file_path:
                self._load_file_into_batch(file_path)
                if not self._batch.items:
                    return
        else:
            folder = Path(input_text)
            if not folder.is_dir():
                QMessageBox.warning(
                    self,
                    "Carpeta inválida",
                    "La ruta seleccionada no es una carpeta válida.",
                )
                return

            if not self._batch.items:
                pass

        self._start_processing()

    # ------------------------------------------------------------------
    # Creación de worker y dependencias
    # ------------------------------------------------------------------

    def _start_processing(self) -> None:
        """Prepara dependencias y lanza el TranscriptionWorker."""
        device = self._current_device()
        LOGGER.info("Iniciando transcripción con dispositivo: %s", device.upper())

        model_name = str(self._config.get("preferences.model_name", "small") or "small")
        compute_type = str(
            self._config.get("preferences.model_compute_type", "auto") or "auto"
        )

        ffmpeg_manager = FFmpegManager()
        ffmpeg_path = ffmpeg_manager.ensure_ffmpeg()
        if ffmpeg_path is None:
            QMessageBox.critical(
                self,
                "Error con FFMPEG",
                "No se pudo preparar FFMPEG. Revisa tu conexión a Internet o permisos.",
            )
            return

        model_manager = ModelManager()
        transcriber = Transcriber(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            model_manager=model_manager,
            ffmpeg_path=str(ffmpeg_path),
        )

        exporter = Exporter()

        jobs: list[TranscriptionJob] = []

        language_mode = str(
            self._config.get("preferences.language_mode", "auto") or "auto"
        )
        language_code = str(
            self._config.get("preferences.fixed_language_code", "es") or "es"
        )
        vad_enabled = bool(self._config.get("preferences.vad_enabled", False))

        output_formats: list[str] = []
        if self._chk_txt.isChecked():
            output_formats.append("txt")
        if self._chk_srt.isChecked():
            output_formats.append("srt")
        if self._chk_vtt.isChecked():
            output_formats.append("vtt")

        if not output_formats:
            output_formats = ["srt"]

        mode = self._get_mode_from_checkboxes()

        if self._get_input_mode() == "folder":
            input_text = self._folder_edit.text().strip()
            folder = Path(input_text)
            self._load_folder_into_batch(folder, output_formats=output_formats)

        for item in self._batch.items:
            if item.status != BatchItemStatus.PENDING:
                continue

            options = {
                "language_mode": language_mode,
                "language_code": language_code,
                "vad_enabled": vad_enabled,
                "mode": mode,
                "device": device,
            }
            jobs.append(
                TranscriptionJob(
                    input_path=item.input_path,
                    transcription_options=options,
                    output_formats=output_formats,
                    task_mode=self._get_task_mode(),
                    output_dir=self._get_output_dir(),
                    max_line_chars=int(self._config.get(
                        "preferences.subtitle_max_line_length", 42)),
                    max_lines_per_segment=int(self._config.get(
                        "preferences.subtitle_max_lines_per_segment", 2)),
                )
            )

        if not jobs:
            QMessageBox.information(
                self,
                "Nada que procesar",
                "No hay archivos pendientes en el batch.",
            )
            return

        self._worker = TranscriptionWorker(
            transcriber=transcriber,
            exporter=exporter,
            batch=self._batch,
            jobs=jobs,
            parent=self,
        )

        self._worker.progress_changed.connect(self._on_worker_progress_changed)
        self._worker.file_progress_changed.connect(self._file_progress_bar.setValue)
        self._worker.file_started.connect(self._on_worker_file_started)
        self._worker.file_finished.connect(self._on_worker_file_finished)
        self._worker.error_occurred.connect(self._on_worker_error_occurred)
        self._worker.finished_all.connect(self._on_worker_finished_all)

        self._start_cancel_button.setText("Cancelar")
        self._start_cancel_button.setEnabled(True)
        self._browse_button.setEnabled(False)
        self._folder_edit.setEnabled(False)
        self._chk_txt.setEnabled(False)
        self._chk_srt.setEnabled(False)
        self._chk_vtt.setEnabled(False)
        self._radio_transcribe.setEnabled(False)
        self._radio_translate.setEnabled(False)
        self._radio_both.setEnabled(False)
        self._btn_settings.setEnabled(False)
        self._chk_output_same.setEnabled(False)
        self._output_dir_edit.setEnabled(False)
        self._btn_browse_output.setEnabled(False)

        self._progress_bar.setValue(0)
        self._file_progress_bar.setValue(0)
        self._refresh_summary_label()
        self._worker.start()

    # ------------------------------------------------------------------
    # Slots del worker
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_worker_progress_changed(self, value: int) -> None:
        """Actualiza la barra de progreso global."""
        self._progress_bar.setValue(value)

    @Slot(Path)
    def _on_worker_file_started(self, path: Path) -> None:
        """Marca un archivo como en progreso en la tabla y actualiza la status bar."""
        self._update_status_for_path(path)
        self._status_right_label.setText(path.name)

    @Slot(Path)
    def _on_worker_file_finished(self, path: Path) -> None:
        """Marca un archivo como completado en la tabla."""
        self._update_status_for_path(path)

    @Slot(str)
    def _on_worker_error_occurred(self, message: str) -> None:
        """Muestra un mensaje de error y refresca la tabla."""
        QMessageBox.warning(self, "Error en transcripción", message)
        self._refresh_batch_table()

    @Slot()
    def _on_worker_finished_all(self) -> None:
        """Restaura el estado de la UI tras finalizar el procesamiento."""
        device = self._current_device()
        LOGGER.info("Transcripción finalizada. Dispositivo usado: %s", device.upper())
        self._refresh_summary_label()
        self._status_right_label.setText("")
        self._file_progress_bar.setValue(0)
        self._refresh_batch_table()

        completed = self._batch.count_by_status(BatchItemStatus.COMPLETED)
        errors = self._batch.count_by_status(BatchItemStatus.ERROR)
        canceled = self._batch.count_by_status(BatchItemStatus.CANCELED)
        skipped = self._batch.count_by_status(BatchItemStatus.SKIPPED)

        if canceled > 0:
            title = "Proceso cancelado"
            lines = ["Proceso cancelado por el usuario."]
        else:
            title = "Transcripción completada"
            lines = ["Transcripción finalizada."]

        if completed:
            lines.append(f"✓  Completados: {completed}")
        if skipped:
            lines.append(f"—  Saltados (ya existían): {skipped}")
        if errors:
            lines.append(f"✗  Errores: {errors}")
        if canceled:
            lines.append(f"—  Cancelados: {canceled}")

        QMessageBox.information(self, title, "\n".join(lines))

        self._start_cancel_button.setText("▶  Iniciar")
        self._start_cancel_button.setEnabled(True)
        self._browse_button.setEnabled(True)
        self._folder_edit.setEnabled(True)
        self._chk_txt.setEnabled(True)
        self._chk_srt.setEnabled(True)
        self._chk_vtt.setEnabled(True)
        self._radio_transcribe.setEnabled(True)
        self._radio_translate.setEnabled(True)
        self._radio_both.setEnabled(True)
        self._btn_settings.setEnabled(True)
        self._chk_output_same.setEnabled(True)
        same = self._chk_output_same.isChecked()
        self._output_dir_edit.setEnabled(not same)
        self._btn_browse_output.setEnabled(not same)

        self._worker = None
