# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Sambhav\\Desktop\\Mojo - Copy\\mojo_changed.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Sambhav\\Desktop\\Mojo - Copy\\mojo_ui.py', '.')],
    hiddenimports=['google.genai', 'PIL', 'pywt'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Mojo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Mojo',
)
