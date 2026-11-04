"""قسم «مخطط الموقع والترسيم» في صفحة الإدخال: قراءة الملف في الخلفية وعرض الحقول للمراجعة."""
import os

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QVBoxLayout, QWidget,
)

from .. import site_plan
from ..dialogs import ImageDialog
from ..theme import C, S2, S3, S4, S6
from ..widgets import Banner, Card, Field, button, grid, icon, label

PLAN_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# الحقول القابلة للتعديل في القسم (رقم القطعة واسم المالك في قسم بيانات المواطن)
EDIT_FIELDS = [
    ("plate", "رقم اللوحة"), ("basin", "الحوض"), ("basinNo", "رقم الحوض"),
    ("hay", "الحي"), ("hayNo", "رقم الحي"), ("village", "القرية"),
    ("parcelArea", "مساحة القطعة (م²)"), ("landUse", "استعمال القطعة"), ("planDate", "تاريخ المخطط"),
]


class _Signals(QObject):
    done = Signal(dict, str)
    failed = Signal(str)


class _ReadJob(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _Signals()

    def run(self):
        try:
            data, method = site_plan.read_site_plan(self.path)
            self.signals.done.emit(data, method)
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(str(e))


def plan_preview(path, width=420):
    """صورة مصغّرة للمخطط (الصفحة الأولى من PDF أو الصورة نفسها)."""
    if path.lower().endswith(".pdf"):
        try:
            img = site_plan.render_first_page(path, width * 2)
        except Exception:  # noqa: BLE001
            img = None
        return QPixmap.fromImage(img) if img is not None else QPixmap()
    return QPixmap(path)


class SitePlanCard(Card):
    """يرسل plan_read عند انتهاء القراءة، و changed عند تعديل الحقول أو إزالة المخطط."""
    plan_read = Signal(dict)
    changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__("مخطط الموقع والترسيم",
                         "أرفق مخطط الموقع (PDF أو صورة) فيُقرأ اسم المالك ورقم القطعة والحوض والحي والمساحة "
                         "وأحكام التنظيم تلقائياً، وتُحفظ مع سجل المواطن.", step=2)
        self.store = store
        self.attachment = None
        self.zoning = {}
        self._job = None
        self.setAcceptDrops(True)

        # فارغ
        self.empty = QFrame()
        self.empty.setObjectName("dropZone")
        ev = QVBoxLayout(self.empty)
        ev.setContentsMargins(S4, S6, S4, S6)
        ev.setSpacing(S2)
        ic = QLabel()
        ic.setPixmap(icon("mdi6.file-document-outline", C["accent_fg"]).pixmap(36, 36))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(ic)
        t = label("اسحب ملف مخطط الموقع إلى هنا أو اختره من جهازك (PDF أو صورة)", "caption")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(t)
        pick = button("قراءة مخطط موقع", None, "mdi6.text-recognition")
        pick.clicked.connect(self.pick)
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(pick)
        r.addStretch(1)
        ev.addLayout(r)
        self.body.addWidget(self.empty)

        # جاري القراءة
        self.busy = QWidget()
        bl = QVBoxLayout(self.busy)
        bl.setContentsMargins(0, S2, 0, S2)
        self.busy_text = label("جاري قراءة المخطط…", "caption")
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bl.addWidget(self.busy_text)
        bl.addWidget(bar)
        self.body.addWidget(self.busy)

        # مع ملف
        self.filled = QWidget()
        h = QHBoxLayout(self.filled)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(S4)
        self.thumb = QLabel()
        self.thumb.setObjectName("cadPreview")
        self.thumb.setFixedSize(210, 272)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb.setToolTip("انقر لعرض المخطط بحجم كبير")
        self.thumb.mouseReleaseEvent = lambda e: self.view()
        h.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(S3)
        self.status = Banner()
        col.addWidget(self.status)
        self.edits = {}
        fields = []
        for key, title in EDIT_FIELDS:
            e = QLineEdit()
            e.textEdited.connect(lambda _=None: self.changed.emit())
            self.edits[key] = e
            fields.append(Field(title, e))
        col.addLayout(grid(fields, 3))
        self.zoning_label = label("", "caption", wrap=True)
        col.addWidget(self.zoning_label)
        btns = QHBoxLayout()
        btns.setSpacing(S2)
        b_open = button("فتح الملف", "secondary", "mdi6.open-in-new")
        b_again = button("إعادة القراءة", "secondary", "mdi6.refresh")
        b_swap = button("استبدال", "secondary", "mdi6.swap-horizontal")
        b_rm = button("إزالة", "danger", "mdi6.trash-can-outline")
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.path())))
        b_again.clicked.connect(lambda: self.read(self.path(), keep_attachment=True))
        b_swap.clicked.connect(self.pick)
        b_rm.clicked.connect(self.remove)
        for b in (b_open, b_again, b_swap):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(b_rm)
        col.addLayout(btns)
        h.addLayout(col, 1)
        self.body.addWidget(self.filled)
        self._show("empty")

    # ---------- الحالة
    def _show(self, state):
        self.empty.setVisible(state == "empty")
        self.busy.setVisible(state == "busy")
        self.filled.setVisible(state == "filled")

    def path(self):
        return self.store.attachment_path(self.attachment) if self.attachment else ""

    def values(self):
        """بيانات المخطط كما تُحفظ في السجل (بعد تعديلات المستخدم)."""
        if not self.attachment:
            return None
        out = {k: e.text().strip() for k, e in self.edits.items() if e.text().strip()}
        if self.zoning:
            out["zoning"] = dict(self.zoning)
        return out

    def set_plan(self, attachment, plan, status=None):
        """تعبئة القسم من سجل محفوظ (أو من قراءة جديدة)."""
        self.attachment = attachment
        plan = plan or {}
        self.zoning = dict(plan.get("zoning") or {})
        for k, e in self.edits.items():
            e.setText(str(plan.get(k) or ""))
        if not attachment:
            self._show("empty")
            return
        pm = plan_preview(self.path())
        if not pm.isNull():
            self.thumb.setPixmap(pm.scaled(QSize(206, 268), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        else:
            self.thumb.setPixmap(icon("mdi6.file-document-outline", C["accent_fg"]).pixmap(48, 48))
        self.zoning_label.setText(zoning_text(self.zoning))
        self.zoning_label.setVisible(bool(self.zoning))
        if status:
            self.status.show_msg(*status, autohide=False)
        else:
            self.status.hide()
        self._show("filled")

    def clear(self):
        self.set_plan(None, None)

    # ---------- الإجراءات
    def pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر مخطط الموقع", os.path.expanduser("~"),
                                              "مخطط موقع (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if path:
            self.read(path)

    def read(self, path, keep_attachment=False):
        if not keep_attachment:
            try:
                self.attachment = self.store.add_attachment(path)
            except OSError as e:
                self.status.show_msg(f"تعذّر نسخ الملف: {e}", "danger", autohide=False)
                return
            path = self.path()
        self.busy_text.setText(f"جاري قراءة «{os.path.basename(path)}»… (الصور تحتاج بضع ثوانٍ)")
        self._show("busy")
        self._job = _ReadJob(path)
        self._job.signals.done.connect(self._on_done)
        self._job.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(self._job)

    def _on_done(self, data, method):
        self._job = None
        n = len([k for k in data if k != "zoning"])
        if n >= 5:
            status = (("تمت قراءة المخطط من ملف PDF ✓ — راجع القيم." if method != "ocr" else
                       "تمت قراءة الصورة (OCR) — راجع القيم وصحّح أي خطأ قبل الحفظ."), "success" if method != "ocr" else "info")
        elif n:
            status = ("قُرئ جزء من البيانات فقط — أكمل الحقول الفارغة يدوياً.", "warning")
        else:
            status = ("لم يُقرأ أي نص من الملف — أدخل البيانات يدوياً.", "warning")
        self.set_plan(self.attachment, data, status)
        self.plan_read.emit(data)

    def _on_failed(self, msg):
        self._job = None
        self.set_plan(self.attachment, {}, (f"تعذّرت قراءة الملف: {msg} — أدخل البيانات يدوياً.", "warning"))
        self.plan_read.emit({})

    def remove(self):
        self.clear()
        self.changed.emit()

    def view(self):
        if not self.attachment:
            return
        pm = plan_preview(self.path(), 1400)
        if not pm.isNull():
            ImageDialog(f"مخطط الموقع — {self.attachment['name']}", pm, self.window()).exec()

    # السحب والإفلات على القسم
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in PLAN_EXTS:
                self.read(p)
                break
        e.acceptProposedAction()


def zoning_text(z):
    if not z:
        return ""
    names = dict(site_plan.ZONING_FIELDS)
    parts = [f"{names[k]}: {z[k]}" for k, _ in site_plan.ZONING_FIELDS if z.get(k)]
    return "أحكام التنظيم — " + " · ".join(parts)
