# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

exe = EXE(
    pyinstaller=True,
    script='main.py',
    base=None,
    icon='appicon.ico',
    name='Shitty Archive Bruteforcer',
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Shitty Archive Bruteforcer'
)
