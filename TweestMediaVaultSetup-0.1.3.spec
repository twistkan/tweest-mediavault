# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['setup_app.py'],
    pathex=[],
    binaries=[],
    datas=[('Branding', 'Branding'), ('D:/CODING WORKS/ChatGPT/Tweest MediaVault/build/payload.zip', '.')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='TweestMediaVaultSetup-0.1.3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Branding/Twisted-logo idea 04.jpg'],
)
