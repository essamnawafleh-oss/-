"""نقطة تشغيل التطبيق."""
import sys

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QApplication

from . import theme
from .data import Store
from .main_window import MainWindow


def create_app(argv=None):
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
    app.setFont(theme.font())
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet())
    return app


def main():
    app = create_app()
    if "--smoke-test" in sys.argv:
        sys.exit(_smoke_test(app))
    store = Store()
    store.purge_orphan_attachments()
    win = MainWindow(store)
    win.show()
    sys.exit(app.exec())


def _smoke_test(app):
    """فحص سريع لنسخة exe المبنية: الملفات المرفقة موجودة والنافذة تُبنى."""
    import os
    import tempfile

    from PySide6.QtCore import QTimer

    from .data import resource_path

    for name in ("app.ico", "diagram_rubble.png", "diagram_reinforced.png", "chevron-down.svg",
                 os.path.join("fonts", "IBMPlexSansArabic_400Regular.ttf")):
        if not os.path.exists(resource_path(name)):
            print("missing asset:", name)
            return 2
    win = MainWindow(Store(tempfile.mkdtemp()))
    win.show()
    for key in win.pages:
        win.go(key)
    QTimer.singleShot(800, app.quit)
    app.exec()
    print("smoke test ok")
    return 0


if __name__ == "__main__":
    main()
