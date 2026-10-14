# -*- mode: python ; coding: utf-8 -*-
# Exe = moteur fige (launcher.py : Python, PySide6, modules standard de
# release_files.RUNTIME_MODULES) ; le code du trainer est copie a cote, dans
# app/, pour etre remplacable par la mise a jour (voir release_files.py).
import os
import shutil
import sys

sys.path.insert(0, SPECPATH)
from release_files import RUNTIME_MODULES, app_files

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=list(RUNTIME_MODULES),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['mgs4trainer', 'mgs4save', 'live_trainer', 'release_files'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MGS4Trainer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/MGS4_Best_Trainer.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MGS4Trainer',
)

# Code du trainer dans dist/MGS4Trainer/app/ (remplace a chaque build).
app_dir = os.path.join(DISTPATH, 'MGS4Trainer', 'app')
shutil.rmtree(app_dir, ignore_errors=True)
for path in app_files():
    target = os.path.join(app_dir, *path.split('/'))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(os.path.join(SPECPATH, *path.split('/')), target)
