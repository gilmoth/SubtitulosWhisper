"""Diálogo de configuración de Subtitulos Whisper.

Responsabilidad: centralizar todas las opciones configurables
(modelo, directorio de descarga, dispositivo CPU/CUDA) en un
diálogo con pestañas, separado de la ventana principal.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..hardware import HardwareDetector
from ..model_manager import AVAILABLE_MODELS, MODEL_METADATA, ModelManager

LOGGER = logging.getLogger(__name__)


def _stars(value: int, total: int = 5) -> str:
    return "●" * value + "○" * (total - value)


class _DownloadWorker(QThread):
    """Hilo de descarga de un modelo Whisper en segundo plano."""

    status_changed = Signal(str)   # mensaje de estado
    finished = Signal(bool)        # True = éxito

    def __init__(self, model_manager: ModelManager, model_name: str, parent=None) -> None:
        super().__init__(parent)
        self._mm = model_manager
        self._model_name = model_name

    def run(self) -> None:
        def _cb(pct: float, msg: str) -> None:
            self.status_changed.emit(msg)

        path = self._mm.download_model(self._model_name, progress_callback=_cb)
        self.finished.emit(path is not None)


class SettingsDialog(QDialog):
    """Diálogo de configuración con pestañas Modelo y Dispositivo."""

    settings_changed = Signal()

    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config

        self.setWindowTitle("Configuración")
        self.setMinimumWidth(620)
        self.setMinimumHeight(460)

        layout = QVBoxLayout(self)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_model_tab(), "  Modelo  ")
        self._tabs.addTab(self._build_device_tab(), "  Dispositivo  ")
        self._tabs.addTab(self._build_audio_tab(), "  Audio  ")
        layout.addWidget(self._tabs)

        close_btn = QPushButton("Cerrar")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._apply_from_config()

    # ------------------------------------------------------------------
    # Construcción de pestañas
    # ------------------------------------------------------------------

    def _build_model_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)

        # Tabla de modelos (7 columnas: radio | estado | nombre | tamaño | velocidad | calidad | VRAM)
        self._model_table = QTableWidget(len(AVAILABLE_MODELS), 7)
        self._model_table.setHorizontalHeaderLabels(
            ["", "", "Modelo", "Tamaño", "Velocidad", "Calidad", "VRAM"]
        )
        self._model_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._model_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._model_table.verticalHeader().setVisible(False)
        self._model_table.setShowGrid(False)
        self._model_table.setAlternatingRowColors(True)
        self._model_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hdr = self._model_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)       # radio
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)       # estado ✓/○
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)       # nombre
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)       # tamaño
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)     # velocidad
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)     # calidad
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)       # VRAM
        self._model_table.setColumnWidth(0, 32)
        self._model_table.setColumnWidth(1, 28)
        self._model_table.setColumnWidth(2, 90)
        self._model_table.setColumnWidth(3, 72)
        self._model_table.setColumnWidth(6, 68)

        # Grupo exclusivo de radio buttons
        self._model_radio_group = QButtonGroup(self)
        self._model_radio_group.setExclusive(True)

        # Altura fija por fila
        for i in range(len(AVAILABLE_MODELS)):
            self._model_table.setRowHeight(i, 26)

        self._model_table.setFixedHeight(26 * len(AVAILABLE_MODELS) + 26)  # filas + cabecera

        layout.addWidget(self._model_table)

        # Descripción del modelo seleccionado
        self._model_desc = QLabel()
        self._model_desc.setWordWrap(True)
        self._model_desc.setStyleSheet(
            "color: #333; font-size: 11px; padding: 4px 2px;"
        )
        self._model_desc.setMinimumHeight(36)
        layout.addWidget(self._model_desc)

        # Fila de descarga
        download_row = QHBoxLayout()
        self._btn_download = QPushButton("⬇  Descargar modelo")
        self._btn_download.setFixedWidth(180)
        self._btn_download.setEnabled(False)
        self._download_progress = QProgressBar()
        self._download_progress.setRange(0, 0)   # indeterminada mientras descarga
        self._download_progress.setFixedHeight(18)
        self._download_progress.setVisible(False)
        self._download_status = QLabel()
        self._download_status.setStyleSheet("color: #555; font-size: 11px;")
        download_row.addWidget(self._btn_download)
        download_row.addWidget(self._download_progress, 1)
        download_row.addWidget(self._download_status, 2)
        layout.addLayout(download_row)

        # Directorio de descarga
        dir_box = QGroupBox("Directorio de descarga de modelos")
        dir_layout = QVBoxLayout(dir_box)

        dir_row = QHBoxLayout()
        self._models_dir_edit = QLineEdit()
        self._models_dir_edit.setPlaceholderText("Ruta donde se guardan los modelos descargados")
        self._btn_browse_dir = QPushButton("Examinar...")
        self._btn_browse_dir.setFixedWidth(100)
        dir_row.addWidget(self._models_dir_edit, 1)
        dir_row.addWidget(self._btn_browse_dir)
        dir_layout.addLayout(dir_row)

        self._dir_info = QLabel()
        self._dir_info.setStyleSheet("color: #555; font-size: 11px;")
        dir_layout.addWidget(self._dir_info)

        layout.addWidget(dir_box)
        layout.addStretch()

        self._btn_browse_dir.clicked.connect(self._on_browse_models_dir)
        self._models_dir_edit.editingFinished.connect(self._on_models_dir_edited)
        self._btn_download.clicked.connect(self._on_download_clicked)

        return w

    def _build_device_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        dev_box = QGroupBox("Dispositivo de procesamiento")
        dev_layout = QVBoxLayout(dev_box)

        radio_row = QHBoxLayout()
        self._radio_cpu = QRadioButton("CPU")
        self._radio_cuda = QRadioButton("CUDA  (GPU NVIDIA)")
        self._radio_cuda.setEnabled(False)
        self._btn_detect = QPushButton("Detectar hardware")
        self._btn_detect.setFixedWidth(140)

        grp = QButtonGroup(self)
        grp.addButton(self._radio_cpu)
        grp.addButton(self._radio_cuda)
        grp.setExclusive(True)
        self._radio_cpu.setChecked(True)

        radio_row.addWidget(self._radio_cpu)
        radio_row.addWidget(self._radio_cuda)
        radio_row.addSpacing(16)
        radio_row.addWidget(self._btn_detect)
        radio_row.addStretch()
        dev_layout.addLayout(radio_row)

        self._device_info = QLabel("Pulsa «Detectar hardware» para comprobar soporte CUDA.")
        self._device_info.setWordWrap(True)
        self._device_info.setStyleSheet("color: #555; font-size: 11px; padding-top: 4px;")
        dev_layout.addWidget(self._device_info)

        layout.addWidget(dev_box)
        layout.addStretch()

        self._radio_cpu.toggled.connect(self._on_device_toggled)
        self._radio_cuda.toggled.connect(self._on_device_toggled)
        self._btn_detect.clicked.connect(self._on_detect_clicked)

        return w

    def _build_audio_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        vad_box = QGroupBox("Voice Activity Detection (VAD)")
        vad_layout = QVBoxLayout(vad_box)

        self._chk_vad = QCheckBox("Activar VAD")
        vad_layout.addWidget(self._chk_vad)

        vad_desc = QLabel(
            "Filtra automáticamente silencios y fragmentos sin voz antes de transcribir. "
            "Whisper solo procesa los tramos con habla real.\n\n"
            "Recomendado si el audio tiene silencios prolongados, ruido de fondo, "
            "música o muchas pausas (reuniones, entrevistas).\n\n"
            "Nota para archivos SRT/VTT: los timestamps siguen siendo correctos, "
            "pero aparecerán saltos de tiempo en los silencios (ej. 00:00:05 → 00:00:23). "
            "Esto es normal y refleja los tramos sin voz.\n\n"
            "No recomendado si el audio es continuo y denso en habla, o si "
            "necesitas subtítulos sin saltos de tiempo."
        )
        vad_desc.setWordWrap(True)
        vad_desc.setStyleSheet(
            "color: #555; font-size: 11px; margin-left: 20px;"
        )
        vad_layout.addWidget(vad_desc)

        layout.addWidget(vad_box)

        # --- Grupo: idioma ---
        lang_box = QGroupBox("Idioma de la grabación")
        lang_layout = QVBoxLayout(lang_box)

        # Fila: auto
        self._radio_lang_auto = QRadioButton("Auto-detectar")
        lang_layout.addWidget(self._radio_lang_auto)

        # Fila: idioma fijo + combo
        fixed_row = QHBoxLayout()
        self._radio_lang_fixed = QRadioButton("Idioma fijo:")
        self._combo_lang = QComboBox()
        for label, code in [
            ("Español", "es"), ("Inglés", "en"), ("Francés", "fr"),
            ("Alemán", "de"), ("Italiano", "it"), ("Portugués", "pt"),
            ("Neerlandés", "nl"), ("Polaco", "pl"), ("Ruso", "ru"),
            ("Chino", "zh"), ("Japonés", "ja"), ("Árabe", "ar"),
        ]:
            self._combo_lang.addItem(label, code)
        self._combo_lang.setEnabled(False)
        fixed_row.addWidget(self._radio_lang_fixed)
        fixed_row.addWidget(self._combo_lang)
        fixed_row.addStretch()
        lang_layout.addLayout(fixed_row)

        # Fila: multilingüe
        self._radio_lang_multi = QRadioButton("Multilingüe")
        lang_layout.addWidget(self._radio_lang_multi)

        lang_group = QButtonGroup(self)
        lang_group.setExclusive(True)
        lang_group.addButton(self._radio_lang_auto)
        lang_group.addButton(self._radio_lang_fixed)
        lang_group.addButton(self._radio_lang_multi)
        self._radio_lang_auto.setChecked(True)

        lang_desc = QLabel(
            "Auto-detectar: Whisper identifica el idioma automáticamente.\n"
            "Idioma fijo: más preciso si conoces el idioma de la grabación.\n"
            "Multilingüe: detecta el idioma segmento a segmento, útil en "
            "grabaciones con mezcla de idiomas."
        )
        lang_desc.setWordWrap(True)
        lang_desc.setStyleSheet("color: #555; font-size: 11px;")
        lang_layout.addWidget(lang_desc)

        layout.addWidget(lang_box)

        # --- Grupo: formato de subtítulos ---
        subs_box = QGroupBox("Formato de subtítulos")
        subs_layout = QVBoxLayout(subs_box)

        # Fila: longitud máxima de línea
        chars_row = QHBoxLayout()
        chars_row.addWidget(QLabel("Caracteres por línea:"))
        self._spin_max_chars = QSpinBox()
        self._spin_max_chars.setRange(20, 120)
        self._spin_max_chars.setValue(42)
        self._spin_max_chars.setSuffix(" caracteres")
        chars_row.addWidget(self._spin_max_chars)
        chars_row.addStretch()
        subs_layout.addLayout(chars_row)

        chars_hint = QLabel(
            "Recomendado: 42 (estándar Netflix/YouTube). "
            "Aumenta si los subtítulos se cortan en tu reproductor."
        )
        chars_hint.setStyleSheet("color: #555; font-size: 11px; margin-left: 4px;")
        subs_layout.addWidget(chars_hint)

        # Fila: líneas por segmento
        lines_row = QHBoxLayout()
        lines_row.addWidget(QLabel("Máximo de líneas:"))
        self._spin_max_lines = QSpinBox()
        self._spin_max_lines.setRange(1, 4)
        self._spin_max_lines.setValue(2)
        lines_row.addWidget(self._spin_max_lines)
        lines_row.addStretch()
        subs_layout.addLayout(lines_row)

        lines_hint = QLabel("Recomendado: 2. Más líneas pueden tapar la imagen.")
        lines_hint.setStyleSheet("color: #555; font-size: 11px; margin-left: 4px;")
        subs_layout.addWidget(lines_hint)

        subs_note = QLabel(
            "Estos ajustes solo afectan a los archivos SRT y VTT. "
            "El archivo TXT no aplica ningún límite de línea."
        )
        subs_note.setWordWrap(True)
        subs_note.setStyleSheet("color: #555; font-size: 11px; margin-top: 4px;")
        subs_layout.addWidget(subs_note)

        layout.addWidget(subs_box)
        layout.addStretch()

        self._chk_vad.toggled.connect(self._on_vad_toggled)
        self._spin_max_chars.valueChanged.connect(self._on_max_chars_changed)
        self._spin_max_lines.valueChanged.connect(self._on_max_lines_changed)
        self._radio_lang_auto.toggled.connect(self._on_lang_mode_changed)
        self._radio_lang_fixed.toggled.connect(self._on_lang_mode_changed)
        self._radio_lang_multi.toggled.connect(self._on_lang_mode_changed)
        self._combo_lang.currentIndexChanged.connect(self._on_lang_code_changed)

        return w

    # ------------------------------------------------------------------
    # Restaurar desde config
    # ------------------------------------------------------------------

    def _apply_from_config(self) -> None:
        self._populate_model_table()
        self._restore_models_dir()
        self._restore_device()
        self._chk_vad.setChecked(
            bool(self._config.get("preferences.vad_enabled", False))
        )
        self._restore_language()
        self._spin_max_chars.setValue(
            int(self._config.get("preferences.subtitle_max_line_length", 42) or 42)
        )
        self._spin_max_lines.setValue(
            int(self._config.get("preferences.subtitle_max_lines_per_segment", 2) or 2)
        )

    def _populate_model_table(self) -> None:
        """Rellena la tabla con todos los modelos y selecciona el guardado."""
        saved = str(self._config.get("preferences.model_name", "small") or "small")
        mm = ModelManager(models_dir=self._configured_models_dir())

        bold_font = QFont()
        bold_font.setBold(True)

        # Limpiar grupo de radios anterior si lo hubiera
        for btn in self._model_radio_group.buttons():
            self._model_radio_group.removeButton(btn)

        self._model_table.blockSignals(True)

        for row, name in enumerate(AVAILABLE_MODELS):
            meta = MODEL_METADATA.get(name, {})
            downloaded = mm.is_downloaded(name)

            # Col 0: radio button de selección
            radio = QRadioButton()
            radio.setStyleSheet("QRadioButton { margin-left: 8px; }")
            radio.toggled.connect(
                lambda checked, n=name: self._on_model_radio_toggled(checked, n)
            )
            self._model_radio_group.addButton(radio, row)
            self._model_table.setCellWidget(row, 0, radio)

            # Col 1: estado descarga ✓/○
            status_item = QTableWidgetItem("✓" if downloaded else "○")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(
                QColor("#1a7f37") if downloaded else QColor("#aaa")
            )

            # Col 2: nombre
            name_item = QTableWidgetItem(name)
            if downloaded:
                name_item.setFont(bold_font)

            # Col 3: tamaño
            size_item = QTableWidgetItem(meta.get("size_label", ""))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Col 4: velocidad
            speed_item = QTableWidgetItem(_stars(meta.get("speed", 0)))
            speed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Col 5: calidad
            quality_item = QTableWidgetItem(_stars(meta.get("quality", 0)))
            quality_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Col 6: VRAM
            vram_item = QTableWidgetItem(f"~{meta.get('vram_gb', '?')} GB")
            vram_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            for col, item in enumerate(
                [status_item, name_item, size_item, speed_item, quality_item, vram_item],
                start=1,
            ):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._model_table.setItem(row, col, item)

            if name == saved:
                radio.setChecked(True)

        self._model_table.blockSignals(False)
        self._update_model_desc(saved)
        self._update_download_button(saved)

    def _restore_models_dir(self) -> None:
        path = str(self._config.get("paths.models_dir", "") or "")
        self._models_dir_edit.setText(path)
        self._update_dir_info()

    def _restore_device(self) -> None:
        device = str(self._config.get("preferences.device_preference", "cpu") or "cpu")
        cuda_name = str(self._config.get("runtime.cuda_device_name", "") or "")

        self._radio_cpu.blockSignals(True)
        self._radio_cuda.blockSignals(True)

        if device == "cuda" and cuda_name:
            self._radio_cuda.setEnabled(True)
            self._radio_cuda.setChecked(True)
            self._radio_cuda.setToolTip(f"GPU: {cuda_name}")
            self._set_device_info_ok(cuda_name)
        else:
            self._radio_cpu.setChecked(True)

        self._radio_cpu.blockSignals(False)
        self._radio_cuda.blockSignals(False)

    # ------------------------------------------------------------------
    # Helpers de modelo
    # ------------------------------------------------------------------

    def _configured_models_dir(self) -> Optional[Path]:
        val = str(self._config.get("paths.models_dir", "") or "")
        return Path(val) if val else None

    def _update_model_desc(self, model_name: str) -> None:
        meta = MODEL_METADATA.get(model_name)
        if not meta:
            self._model_desc.setText("")
            return
        self._model_desc.setText(meta["desc"])

    def _update_dir_info(self) -> None:
        path_str = self._models_dir_edit.text().strip()
        if not path_str:
            self._dir_info.setText("")
            return
        p = Path(path_str)
        try:
            if p.exists():
                mm = ModelManager(models_dir=p)
                downloaded = mm.get_downloaded_models()
                names = ", ".join(downloaded) if downloaded else "—"
                self._dir_info.setText(
                    f"Carpeta existente  ·  {len(downloaded)} modelo(s) descargado(s): {names}"
                )
            else:
                self._dir_info.setText("La carpeta no existe aún (se creará al descargar un modelo)")
        except Exception:
            self._dir_info.setText("")

    def _refresh_table_status(self) -> None:
        """Actualiza los indicadores ✓/○ de la tabla según el directorio actual."""
        mm = ModelManager(models_dir=self._configured_models_dir())
        bold_font = QFont()
        bold_font.setBold(True)
        normal_font = QFont()

        for row, name in enumerate(AVAILABLE_MODELS):
            downloaded = mm.is_downloaded(name)
            status_item = self._model_table.item(row, 1)   # col 1: estado
            name_item = self._model_table.item(row, 2)     # col 2: nombre
            if status_item:
                status_item.setText("✓" if downloaded else "○")
                status_item.setForeground(
                    QColor("#1a7f37") if downloaded else QColor("#aaa")
                )
            if name_item:
                name_item.setFont(bold_font if downloaded else normal_font)

    # ------------------------------------------------------------------
    # Helpers de dispositivo
    # ------------------------------------------------------------------

    def _set_device_info_ok(self, gpu_name: str) -> None:
        self._device_info.setText(f"GPU detectada: {gpu_name}")
        self._device_info.setStyleSheet("color: #1a7f37; font-size: 11px; padding-top: 4px;")

    def _set_device_info_error(self, detail: str) -> None:
        self._device_info.setText(f"CUDA no disponible. {detail}")
        self._device_info.setStyleSheet("color: #c0392b; font-size: 11px; padding-top: 4px;")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(bool, str)
    def _on_model_radio_toggled(self, checked: bool, name: str) -> None:
        """Guarda el modelo seleccionado y actualiza la descripción."""
        if not checked:
            return
        self._config.set("preferences.model_name", name)
        self._config.save()
        self._update_model_desc(name)
        self._update_download_button(name)
        self.settings_changed.emit()

    def _update_download_button(self, model_name: str) -> None:
        """Activa o desactiva el botón de descarga según si el modelo ya existe."""
        mm = ModelManager(models_dir=self._configured_models_dir())
        already = mm.is_downloaded(model_name)
        meta = MODEL_METADATA.get(model_name, {})
        size = meta.get("size_label", "")
        if already:
            self._btn_download.setText("✓  Ya descargado")
            self._btn_download.setEnabled(False)
        else:
            label = f"⬇  Descargar  {model_name}"
            if size:
                label += f"  ({size})"
            self._btn_download.setText(label)
            self._btn_download.setEnabled(True)
        self._download_status.setText("")
        self._download_progress.setVisible(False)

    @Slot()
    def _on_download_clicked(self) -> None:
        """Inicia la descarga del modelo seleccionado en un hilo secundario."""
        model_name = str(self._config.get("preferences.model_name", "small") or "small")
        mm = ModelManager(models_dir=self._configured_models_dir())

        self._btn_download.setEnabled(False)
        self._model_radio_group.setExclusive(False)
        for btn in self._model_radio_group.buttons():
            btn.setEnabled(False)
        self._model_radio_group.setExclusive(True)
        self._btn_browse_dir.setEnabled(False)
        self._models_dir_edit.setEnabled(False)

        self._download_progress.setVisible(True)
        self._download_status.setText(f"Descargando '{model_name}'…")
        self._download_status.setStyleSheet("color: #555; font-size: 11px;")

        self._download_worker = _DownloadWorker(mm, model_name, parent=self)
        self._download_worker.status_changed.connect(self._on_download_status)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()

    @Slot(str)
    def _on_download_status(self, message: str) -> None:
        self._download_status.setText(message)

    @Slot(bool)
    def _on_download_finished(self, success: bool) -> None:
        """Restaura la UI y refresca el estado de la tabla tras la descarga."""
        self._download_progress.setVisible(False)
        for btn in self._model_radio_group.buttons():
            btn.setEnabled(True)
        self._btn_browse_dir.setEnabled(True)
        self._models_dir_edit.setEnabled(True)

        model_name = str(self._config.get("preferences.model_name", "small") or "small")
        if success:
            self._download_status.setText(f"✓  Modelo '{model_name}' descargado correctamente.")
            self._download_status.setStyleSheet("color: #1a7f37; font-size: 11px;")
        else:
            self._download_status.setText("✗  Error durante la descarga. Comprueba la conexión.")
            self._download_status.setStyleSheet("color: #c0392b; font-size: 11px;")
            self._btn_download.setEnabled(True)

        self._refresh_table_status()
        self._update_download_button(model_name)
        if success:
            self.settings_changed.emit()

    def _restore_language(self) -> None:
        """Restaura el modo de idioma y el código fijo desde la configuración."""
        mode = str(self._config.get("preferences.language_mode", "auto") or "auto")
        code = str(self._config.get("preferences.fixed_language_code", "es") or "es")

        for radio, key in (
            (self._radio_lang_auto, "auto"),
            (self._radio_lang_fixed, "single"),
            (self._radio_lang_multi, "multi"),
        ):
            radio.blockSignals(True)
            radio.setChecked(mode == key)
            radio.blockSignals(False)

        self._combo_lang.setEnabled(mode == "single")

        idx = self._combo_lang.findData(code)
        if idx >= 0:
            self._combo_lang.setCurrentIndex(idx)

    @Slot(bool)
    def _on_vad_toggled(self, checked: bool) -> None:
        self._config.set("preferences.vad_enabled", checked)
        self._config.save()
        self.settings_changed.emit()

    @Slot(int)
    def _on_max_chars_changed(self, value: int) -> None:
        self._config.set("preferences.subtitle_max_line_length", value)
        self._config.save()
        self.settings_changed.emit()

    @Slot(int)
    def _on_max_lines_changed(self, value: int) -> None:
        self._config.set("preferences.subtitle_max_lines_per_segment", value)
        self._config.save()
        self.settings_changed.emit()

    @Slot(bool)
    def _on_lang_mode_changed(self, checked: bool) -> None:
        if not checked:
            return
        if self._radio_lang_fixed.isChecked():
            mode = "single"
        elif self._radio_lang_multi.isChecked():
            mode = "multi"
        else:
            mode = "auto"
        self._combo_lang.setEnabled(mode == "single")
        self._config.set("preferences.language_mode", mode)
        self._config.save()
        self.settings_changed.emit()

    @Slot(int)
    def _on_lang_code_changed(self, _: int) -> None:
        code = self._combo_lang.currentData()
        if code:
            self._config.set("preferences.fixed_language_code", code)
            self._config.save()
            self.settings_changed.emit()

    @Slot()
    def _on_browse_models_dir(self) -> None:
        current = self._models_dir_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar directorio de modelos", current or ""
        )
        if folder:
            self._models_dir_edit.setText(folder)
            self._save_models_dir(folder)

    @Slot()
    def _on_models_dir_edited(self) -> None:
        self._save_models_dir(self._models_dir_edit.text().strip())

    def _save_models_dir(self, path_str: str) -> None:
        self._config.set("paths.models_dir", path_str)
        self._config.save()
        self._update_dir_info()
        self._refresh_table_status()
        self.settings_changed.emit()

    @Slot()
    def _on_device_toggled(self) -> None:
        if self.sender() and not self.sender().isChecked():  # type: ignore[union-attr]
            return
        device = "cuda" if self._radio_cuda.isChecked() else "cpu"
        self._config.set("preferences.device_preference", device)
        self._config.save()
        self.settings_changed.emit()

    @Slot()
    def _on_detect_clicked(self) -> None:
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

            self._radio_cuda.setEnabled(True)
            self._radio_cuda.setChecked(True)
            self._radio_cuda.setToolTip(f"GPU: {gpu_label}")
            self._set_device_info_ok(gpu_label)

            self._config.set("runtime.cuda_device_name", gpu_label)
            self._config.set("preferences.device_preference", "cuda")
            self._config.save()
            LOGGER.info("CUDA detectado: %s", gpu_label)
        else:
            detail = ""
            try:
                import ctranslate2  # type: ignore[import-not-found]
                count = ctranslate2.get_cuda_device_count()
                detail = f"ctranslate2 reporta {count} GPU(s) CUDA."
            except Exception as e:
                detail = f"No se pudo verificar ctranslate2: {e}"

            self._set_device_info_error(detail)
            self._radio_cpu.setChecked(True)
            QMessageBox.information(
                self,
                "CUDA no disponible",
                f"No se detectó ninguna GPU CUDA compatible.\n\n{detail}",
            )
            LOGGER.warning("CUDA no disponible: %s", detail)

        self.settings_changed.emit()
