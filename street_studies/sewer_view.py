"""نافذة فحص الصرف الصحي: الإعدادات وجدول القطع ودخلات الخدمات المقترحة."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from . import sewer
from .theme import S3, S4
from .widgets import Banner, Field, NumberEdit, button, grid, label

STATUS_COLOR = {sewer.SERVED: "#2E7D32", sewer.DEEPEN: "#EF6C00", sewer.LANE: "#C62828",
                sewer.NO_OUTLET: "#6A1B9A", sewer.NO_DATA: "#78909C"}


def lot_rows(res):
    """أسطر جدول القطع (تُستخدم في النافذة والتقرير)."""
    rows = []
    for r in res["lots"]:
        st = r["status"]
        detail = ""
        if st == sewer.DEEPEN:
            detail = f"عمق الخط المطلوب {r['needed_depth']:.2f} م"
        elif st == sewer.LANE:
            ln = r["lane"]
            to = "وادٍ" if ln["kind"] == "wadi" else "شارع"
            detail = f"دخلة {ln['width']:g} م بطول {ln['length']:.0f} م إلى {to} ({ln['name']})"
            if ln.get("deepen"):
                detail += " — مع تعميق عند المصب"
        rows.append([r["num"], sewer.STATUS_TEXT[st],
                     f"{r['low'][2]:.2f}" if r.get("low") else "—",
                     f"{r['invert']:.2f}" if r.get("invert") is not None else "—",
                     f"{r['arrive']:.2f}" if r.get("arrive") is not None else "—",
                     f"{r['conn_len']:.0f}" if r.get("conn_len") is not None else "—", detail])
    return rows


HEADERS = ["القطعة", "الحالة", "أوطأ نقطة", "قاع خط الشارع", "منسوب وصول الوصلة", "طول الوصلة (م)", "التفاصيل"]


class SewerDialog(QDialog):
    apply_requested = Signal(dict)

    def __init__(self, run, params=None, parent=None):
        """run(params) ترجع نتيجة sewer.analyze."""
        super().__init__(parent)
        self.setWindowTitle("فحص الصرف الصحي ودخلات الخدمات")
        self.run = run
        p = dict(sewer.DEFAULTS, **(params or {}))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4, S4, S4, S4)
        lay.setSpacing(S3)
        lay.addWidget(label("خدمة القطع بالصرف الصحي من جهة الشارع", "sectionTitle"))
        lay.addWidget(label("الوصلة تبدأ من أوطأ نقطة في القطعة وتنحدر إلى خط المجاري في محور الشارع (المنسوب التصميمي "
                            "من البروفايل إن وُجد). إن تعذّر ذلك حتى مع تعميق الخط، تُقترح دخلة خدمات إلى أقرب مصرف أوطأ.",
                            "caption", wrap=True))
        self.f = {}
        fields = []
        for key, title, scale in (("sewer_depth", "عمق قاع خط الشارع (م)", 1), ("max_depth", "أقصى عمق للخط (م)", 1),
                                  ("conn_slope", "أقل ميل للوصلة (%)", 100), ("start_depth", "عمق بداية الوصلة (م)", 1),
                                  ("lane_width", "عرض دخلة الخدمات (م)", 1), ("search_radius", "مدى البحث عن مصرف (م)", 1)):
            e = NumberEdit()
            e.set_value(round(p[key] * scale, 3))
            self.f[key] = (e, scale)
            fields.append(Field(title, e))
        top = QHBoxLayout()
        top.addLayout(grid(fields, 3), 1)
        again = button("إعادة الفحص", "secondary", "mdi6.refresh")
        again.clicked.connect(self.recompute)
        top.addWidget(again, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(top)
        self.banner = Banner()
        lay.addWidget(self.banner)
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(len(HEADERS) - 1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = button("إغلاق", "secondary")
        close.clicked.connect(self.reject)
        self.apply_btn = button("عرض على المخطط واعتماد النتيجة", "success", "mdi6.check")
        self.apply_btn.clicked.connect(self._apply)
        btns.addWidget(close)
        btns.addWidget(self.apply_btn)
        lay.addLayout(btns)
        self.resize(1080, 620)
        self.result = None
        self.recompute()

    def params(self):
        return {k: (e.value() / s if e.text() else sewer.DEFAULTS[k]) for k, (e, s) in self.f.items()}

    def recompute(self):
        try:
            self.result = self.run(self.params())
        except ValueError as e:
            self.result = None
            self.banner.show_msg(str(e), "danger", autohide=False)
            self.apply_btn.setEnabled(False)
            return
        res = self.result
        self.apply_btn.setEnabled(bool(res["lots"]))
        rows = lot_rows(res)
        self.table.setRowCount(len(rows))
        for i, (row, r) in enumerate(zip(rows, res["lots"])):
            for c, v in enumerate(row):
                it = QTableWidgetItem(v)
                if c == 1:
                    it.setForeground(QColor(STATUS_COLOR[r["status"]]))
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.table.setItem(i, c, it)
        c = res["counts"]
        if not res["lots"]:
            self.banner.show_msg("لا توجد قطع مطلة على الشارع المرسوم في المخطط التنظيمي.", "warning", autohide=False)
            return
        msg = (f"{len(res['lots'])} قطعة: مخدومة {c[sewer.SERVED]} · بتعميق الخط {c[sewer.DEEPEN]} · "
               f"تحتاج دخلة خدمات {c[sewer.LANE]}")
        if c[sewer.NO_OUTLET]:
            msg += f" · بلا مصرف قريب {c[sewer.NO_OUTLET]}"
        if c[sewer.NO_DATA]:
            msg += f" · خارج الكنتور {c[sewer.NO_DATA]}"
        kind = "success" if c[sewer.LANE] + c[sewer.NO_OUTLET] == 0 else "warning"
        self.banner.show_msg(msg, kind, autohide=False)

    def _apply(self):
        if self.result:
            self.apply_requested.emit(self.result)
            self.accept()
