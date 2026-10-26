"""نوافذ منبثقة: عرض المخططات والصور، وتأكيد الحذف."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
)

from .theme import S2, S3, S4, S6
from .widgets import button, label


class ImageDialog(QDialog):
    """يعرض صورة بعرض النافذة، مع تكبير/تصغير."""

    def __init__(self, title, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.pix = QPixmap(image_path)
        self.zoom = 1.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4, S4, S4, S4)
        lay.setSpacing(S3)

        head = QHBoxLayout()
        head.setSpacing(S2)
        head.addWidget(label(title, "sectionTitle"), 1)
        zin = button("", "secondary", "mdi6.magnify-plus-outline")
        zout = button("", "secondary", "mdi6.magnify-minus-outline")
        fit = button("ملء العرض", "secondary", "mdi6.fit-to-page-outline")
        close = button("إغلاق", None, "mdi6.close")
        zin.setToolTip("تكبير")
        zout.setToolTip("تصغير")
        zin.clicked.connect(lambda: self._zoom(1.25))
        zout.clicked.connect(lambda: self._zoom(0.8))
        fit.clicked.connect(self._fit)
        close.clicked.connect(self.accept)
        for b in (zout, zin, fit, close):
            head.addWidget(b)
        lay.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img = QLabel()
        self.img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img.setStyleSheet("background:#FFFFFF; border:1px solid #E0E6E9; border-radius:8px;")
        self.scroll.setWidget(self.img)
        lay.addWidget(self.scroll, 1)

        scr = (parent.screen() if parent else self.screen()).availableGeometry()
        self.resize(min(1100, int(scr.width() * 0.85)), min(820, int(scr.height() * 0.88)))
        self._fit()

    def _render(self):
        if self.pix.isNull():
            self.img.setText("تعذّر عرض الصورة")
            return
        w = max(100, int(self.pix.width() * self.zoom))
        self.img.setPixmap(self.pix.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation))
        self.img.adjustSize()

    def _zoom(self, f):
        self.zoom = max(0.1, min(4.0, self.zoom * f))
        self._render()

    def _fit(self):
        if not self.pix.isNull():
            avail = self.scroll.viewport().width() - 4 if self.isVisible() else self.width() - 2 * S6
            self.zoom = max(0.1, avail / self.pix.width())
        self._render()

    def showEvent(self, e):
        super().showEvent(e)
        self._fit()


class ConfirmDialog(QDialog):
    def __init__(self, title, message, confirm_text="حذف", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S6, S6, S6, S4 + 4)
        lay.setSpacing(S3)
        lay.addWidget(label(title, "sectionTitle"))
        lay.addWidget(label(message, wrap=True))
        lay.addSpacing(S2)
        row = QHBoxLayout()
        row.setSpacing(S2)
        row.addStretch(1)
        cancel = button("إلغاء", "secondary")
        ok = button(confirm_text, "dangerSolid", "mdi6.trash-can-outline")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        cancel.setFocus()
