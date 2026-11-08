"""نافذة تجمع مياه الأمطار والأودية المقترحة."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout,
)

from . import drainage
from .theme import S3, S4
from .widgets import Banner, Field, NumberEdit, button, grid, label

SAG_HEADERS = ["#", "المسافة على الشارع (م)", "المنسوب", "المساحة الصابة (هكتار)", "التدفق (م³/ث)",
               "المصب", "طول دخلة التصريف (م)", "القناة المقترحة (عرض×عمق م)"]
WADI_HEADERS = ["#", "الطول (م)", "المساحة الصابة (هكتار)", "التدفق عند المصب (م³/ث)", "الميل",
                "المقطع الثابت (عرض×عمق م)", "السرعة (م/ث)", "ملاحظة"]


def _ch(c):
    return f"{c['width']:g} × {c['depth']:g}"


def sag_rows(res):
    return [[str(n), f"{s['s']:g}", f"{s['z']:.2f}", f"{s['area'] / 1e4:.2f}", f"{s['q']:.3f}", s["outlet"],
             f"{s['lane_len']:.0f}", _ch(s["channel"])] for n, s in enumerate(res["sags"], 1)]


def wadi_rows(res):
    rows = []
    for n, w in enumerate(res["wadis"], 1):
        c = w["channel"]
        note = "سرعة عالية — يلزم مساقط لتكسير الطاقة" if c.get("drops") else ""
        rows.append([str(n), f"{w['length']:.0f}", f"{w['area'] / 1e4:.2f}", f"{w['q']:.3f}",
                     f"{w['slope'] * 100:.1f}%", _ch(c), f"{c['velocity']:.2f}", note])
    return rows


def _table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    hh = t.horizontalHeader()
    hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    hh.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)
    return t


def _fill(t, rows, warn_col=None):
    t.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for c, v in enumerate(row):
            it = QTableWidgetItem(v)
            if warn_col is not None and c == warn_col and v:
                it.setForeground(QColor("#C62828"))
            t.setItem(i, c, it)


class DrainageDialog(QDialog):
    apply_requested = Signal(dict)

    def __init__(self, run, params=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تجمع مياه الأمطار والأودية")
        self.run = run
        p = dict(drainage.DEFAULTS, **(params or {}))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4, S4, S4, S4)
        lay.setSpacing(S3)
        lay.addWidget(label("تجمع مياه الأمطار على الشارع والأودية المقترحة", "sectionTitle"))
        lay.addWidget(label("نقاط التجمع هي أوطأ نقاط البروفايل الطولي؛ يُتتبّع الجريان منها نزولاً حتى أقرب وادٍ أو شارع "
                            "(دخلة تصريف). الأودية تُستخرج من الكنتور حيث تتجاوز المساحة الصابة الحد، ولكل وادٍ مقطع "
                            "ثابت محسوب من تدفقه عند المصب (Q = 0.278·C·i·A) ومعادلة ماننغ.", "caption", wrap=True))
        self.f = {}
        fields = []
        for key, title in (("runoff_c", "معامل الجريان C"), ("intensity", "شدة المطر (مم/ساعة)"),
                           ("stream_ha", "أقل مساحة صابة للوادي (هكتار)"), ("manning_n", "معامل ماننغ n"),
                           ("max_velocity", "أقصى سرعة (م/ث)"), ("margin", "المنطقة حول الشارع (م)")):
            e = NumberEdit()
            e.set_value(p[key])
            self.f[key] = e
            fields.append(Field(title, e))
        top = QHBoxLayout()
        top.addLayout(grid(fields, 3), 1)
        again = button("إعادة الحساب", "secondary", "mdi6.refresh")
        again.clicked.connect(self.recompute)
        top.addWidget(again, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(top)
        self.banner = Banner()
        lay.addWidget(self.banner)
        self.tabs = QTabWidget()
        self.sag_t = _table(SAG_HEADERS)
        self.wadi_t = _table(WADI_HEADERS)
        self.tabs.addTab(self.sag_t, "نقاط تجمع الأمطار على الشارع")
        self.tabs.addTab(self.wadi_t, "الأودية المقترحة")
        lay.addWidget(self.tabs, 1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = button("إغلاق", "secondary")
        close.clicked.connect(self.reject)
        self.apply_btn = button("عرض على المخطط واعتماد النتيجة", "success", "mdi6.check")
        self.apply_btn.clicked.connect(self._apply)
        btns.addWidget(close)
        btns.addWidget(self.apply_btn)
        lay.addLayout(btns)
        self.resize(1120, 640)
        self.result = None
        self.recompute()

    def params(self):
        return {k: (e.value() if e.text() else drainage.DEFAULTS[k]) for k, e in self.f.items()}

    def recompute(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.result = self.run(self.params())
        except ValueError as e:
            self.result = None
            self.banner.show_msg(str(e), "danger", autohide=False)
            self.apply_btn.setEnabled(False)
            return
        finally:
            QApplication.restoreOverrideCursor()
        res = self.result
        _fill(self.sag_t, sag_rows(res))
        _fill(self.wadi_t, wadi_rows(res), warn_col=len(WADI_HEADERS) - 1)
        self.apply_btn.setEnabled(True)
        fast = sum(1 for w in res["wadis"] if w["channel"].get("drops"))
        msg = (f"{len(res['sags'])} نقطة تجمع على الشارع · {len(res['wadis'])} وادٍ مقترح "
               f"(دقة النموذج {res['cell']:g} م)")
        if fast:
            msg += f" · {fast} وادٍ بسرعة عالية يحتاج مساقط"
        self.banner.show_msg(msg, "warning" if fast else "info", autohide=False)

    def _apply(self):
        if self.result:
            self.apply_requested.emit(self.result)
            self.accept()
