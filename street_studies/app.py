"""نقطة تشغيل التطبيق."""
import sys

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QApplication

from . import theme
from .data import Store
from .main_window import MainWindow
from .settings import Settings


def create_app(argv=None, settings=None):
    if sys.platform == "win32":
        try:  # أيقونة التطبيق في شريط المهام بدل أيقونة بايثون
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hamadeen.StreetStudies")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("StreetStudies")
    app.setApplicationDisplayName("تطبيق دراسات الشوارع الذكي")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    QLocale.setDefault(QLocale(QLocale.Language.Arabic, QLocale.Country.Jordan))
    app.setStyle("Fusion")
    theme.load_fonts()
    theme.apply(app, settings if settings is not None else Settings())
    return app


def main():
    if "--smoke-test" in sys.argv:
        sys.exit(_smoke_test(create_app()))
    settings = Settings()
    app = create_app(settings=settings)
    store = Store()
    store.purge_orphan_attachments()
    win = MainWindow(store, settings)
    win.show()
    sys.exit(app.exec())


def _smoke_test(app):
    """فحص سريع لنسخة exe المبنية: الملفات المرفقة موجودة والنافذة تُبنى."""
    import os
    import tempfile

    from PySide6.QtCore import QTimer

    from .data import resource_path

    for name in ("app.ico", "diagram_rubble.png", "diagram_reinforced.png",
                 os.path.join("fonts", "IBMPlexSansArabic_400Regular.ttf")):
        if not os.path.exists(resource_path(name)):
            print("missing asset:", name)
            return 2
    tmp = tempfile.mkdtemp()
    win = MainWindow(Store(tmp), Settings(tmp))
    win.show()
    for key in list(win.pages):
        win.go(key)
    win.settings["theme"] = "graphite"
    win.apply_appearance()
    # قراءة ورسم ملف DXF وتصدير تقرير PDF (يتأكد أن ezdxf مضمّنة)
    import ezdxf

    from . import dxf_render, report
    dxf = os.path.join(tmp, "t.dxf")
    doc = ezdxf.new()
    doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 8), (0, 8)], close=True)
    doc.saveas(dxf)
    img, err = dxf_render.render_file(dxf, 200, 150)
    if img is None:
        print("dxf failed:", err)
        return 3
    st = win.store
    st.streets.append({"name": "اختبار", "length": 10, "width": 5, "quantities": {},
                       "parcel": st.add_attachment(dxf), "attachments": []})
    folder = report.export_report(st, st.streets[-1], tmp)
    if not os.path.exists(os.path.join(folder, "اختبار.pdf")):
        print("report failed")
        return 4
    QTimer.singleShot(800, app.quit)
    app.exec()
    print("smoke test ok")
    return 0


if __name__ == "__main__":
    main()
