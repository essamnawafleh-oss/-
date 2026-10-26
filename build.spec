# -*- mode: python ; coding: utf-8 -*-
# بناء التطبيق:  pyinstaller build.spec   (الناتج في dist/StreetStudies)
from PyInstaller.utils.hooks import collect_data_files

datas = [("street_studies/assets", "street_studies/assets")] + collect_data_files("qtawesome")
excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
            "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
            "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth"]

a = Analysis(["run.py"], datas=datas, excludes=excludes, noarchive=False)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="StreetStudies", console=False,
          icon="street_studies/assets/app.ico", version="version_info.txt")
coll = COLLECT(exe, a.binaries, a.datas, name="StreetStudies")
