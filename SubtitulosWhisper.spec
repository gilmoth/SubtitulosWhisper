# -*- mode: python ; coding: utf-8 -*-
#
# SubtitulosWhisper.spec
# Genera un directorio distribuible (onedir) para Windows.
#
# Uso:
#   pyinstaller SubtitulosWhisper.spec
#
# Dependencias externas gestionadas en tiempo de ejecución (NO embebidas):
#   - ffmpeg/ffprobe  → se descarga automáticamente por FFmpegManager
#   - Modelos Whisper → se descargan/seleccionan desde la UI
#
# Si PyInstaller no recoge automáticamente ctranslate2 o PySide6,
# instala primero el hook extra:
#   pip install pyinstaller-hooks-contrib
# ---------------------------------------------------------------------------

from PyInstaller.utils.hooks import collect_all, collect_data_files

# --- PySide6: recoge todos los binarios, plugins y módulos Qt ---
pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all('PySide6')

# --- ctranslate2: librería nativa de faster-whisper (DLLs CUDA incluidas) ---
ct2_datas, ct2_binaries, ct2_hiddenimports = collect_all('ctranslate2')

# --- faster_whisper: assets propios (tokenizer config, etc.) ---
fw_datas = collect_data_files('faster_whisper')

# --- tokenizers / huggingface_hub: assets del tokenizador ---
tok_datas = collect_data_files('tokenizers')
hf_datas  = collect_data_files('huggingface_hub')

# ---------------------------------------------------------------------------

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[] + pyside6_binaries + ct2_binaries,
    datas=[
        # Icono de la aplicación
        ('app/ui/resources/icon.ico', 'app/ui/resources'),
        # Assets de los paquetes
        *pyside6_datas,
        *ct2_datas,
        *fw_datas,
        *tok_datas,
        *hf_datas,
    ],
    hiddenimports=[
        # ctranslate2 (detección CUDA vía get_cuda_device_count)
        'ctranslate2',
        # faster-whisper
        'faster_whisper',
        'faster_whisper.audio',
        'faster_whisper.transcribe',
        'faster_whisper.tokenizer',
        'faster_whisper.utils',
        # PySide6 módulos usados explícitamente
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # requests (descarga de ffmpeg)
        'requests',
        'requests.adapters',
        'requests.packages.urllib3',
        # Módulos de la app
        'app',
        'app.batch',
        'app.config',
        'app.exporter',
        'app.ffmpeg_manager',
        'app.hardware',
        'app.model_manager',
        'app.paths',
        'app.transcriber',
        'app.worker',
        'app.ui.ui_main',
        'app.ui.settings_dialog',
        *pyside6_hiddenimports,
        *ct2_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Excluir lo que no se usa para reducir tamaño
        'torch',
        'torchvision',
        'torchaudio',
        'torch._C',
        'tkinter',
        'matplotlib',
        'numpy.distutils',
        'scipy',
        'IPython',
        'notebook',
        'PIL',
        'triton',
        'onnxruntime',
        'jinja2',
        'sympy',
        'networkx',
        'pandas',
        'sklearn',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SubtitulosWhisper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed=True → sin ventana de consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/ui/resources/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        # No comprimir las DLLs de Qt ni ctranslate2 (pueden fallar con UPX)
        'Qt6Core.dll',
        'Qt6Gui.dll',
        'Qt6Widgets.dll',
        'ctranslate2.dll',
        'cublas64_*.dll',
        'cudnn_*.dll',
    ],
    name='SubtitulosWhisper',
)
