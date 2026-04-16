# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for squid-tools.

Run from the installer/ directory:
  cd installer && python -m PyInstaller squid_tools.spec --noconfirm

Based on ndviewer_light's proven bundling pattern.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files
napari_datas = collect_data_files("napari")
vispy_datas = collect_data_files("vispy")
pydantic_datas = collect_data_files("pydantic")

# Collect all submodules to ensure complete bundling
squid_tools_imports = collect_submodules("squid_tools")
napari_imports = collect_submodules("napari")
vispy_imports = collect_submodules("vispy")

a = Analysis(
    ["entry.py"],
    pathex=[os.path.abspath("..")],
    binaries=[],
    datas=napari_datas + vispy_datas + pydantic_datas,
    hiddenimports=squid_tools_imports
    + napari_imports
    + vispy_imports
    + [
        "PyQt5",
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "PyQt5.QtWidgets",
        "superqt",
        "dask",
        "dask.array",
        "tifffile",
        "pydantic",
        "pydantic.deprecated",
        "yaml",
        "zarr",
        "numpy",
        "numpy.core._methods",
        "numpy.lib.format",
        "xml.etree.ElementTree",
        "importlib.metadata",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="squid-tools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="squid-tools",
)
