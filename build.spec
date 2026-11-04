# -*- mode: python ; coding: utf-8 -*-
# بناء التطبيق:  pyinstaller build.spec   (الناتج في dist/StreetStudies)
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = ([("street_studies/assets", "street_studies/assets")] + collect_data_files("qtawesome")
         + collect_data_files("ezdxf"))
hiddenimports = [m for m in collect_submodules("ezdxf") if ".addons." not in m]
# محرك قراءة الصور (Tesseract + العربية) — يُجهَّز في vendor/tesseract أثناء البناء على ويندوز
if os.path.isdir("vendor/tesseract"):
    datas.append(("vendor/tesseract", "street_studies/assets/tesseract"))
excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
            "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
            "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth"]

a = Analysis(["run.py"], datas=datas, hiddenimports=hiddenimports, excludes=excludes + ["matplotlib"],
             noarchive=False)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="StreetStudies", console=False,
          icon="street_studies/assets/app.ico", version="version_info.txt")
coll = COLLECT(exe, a.binaries, a.datas, name="StreetStudies")
