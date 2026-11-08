"""نافذة الإفراز: اقتراح تلقائي أو فحص قطع مرسومة، مع جدول النتائج."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from . import subdivision
from .sewer import STATUS_TEXT
from .theme import S3, S4
from .widgets import Banner, ChoiceGroup, Field, NumberEdit, button, grid, label

HEADERS = ["#", "المساحة (م²)", "الواجهة (م)", "الصرف الصحي", "الملاحظات"]


def lot_rows(res):
    return [[str(r["n"]), f"{r['area']:.0f}", f"{r['frontage']:.1f}",
             STATUS_TEXT.get(r.get("sewer"), "—") if r.get("sewer") else "—",
             "، ".join(r["reasons"]) or "مطابقة ✓"] for r in res["lots"]]


def internal_lines(res):
    out = []
    for n, it in enumerate(res.get("internal") or [], 1):
        pr = it.get("profile")
        if not pr:
            out.append(f"الشارع الداخلي {n}: خارج منطقة الكنتور")
            continue
        out.append(f"الشارع الداخلي {n}: طول {pr['length']:.0f} م · أقصى ميل تصميمي {pr['max_design_grade'] * 100:.1f}% "
                   f"· أقصى قطع {pr['max_cut']:.1f} م / ردم {pr['max_fill']:.1f} م"
                   + (f" · ⚠ {pr['design_over']} مقطع ميل و{pr['cf_over']} نقطة قطع/ردم مخالفة"
                      if pr["design_over"] or pr["cf_over"] else " ✓"))
    return out


class SubdivisionDialog(QDialog):
    apply_requested = Signal(dict)

    def __init__(self, run, has_drawn, params=None, parent=None):
        """run(mode, params) ترجع {'proposal': ..., 'check': ...}."""
        super().__init__(parent)
        self.setWindowTitle("الإفراز")
        self.run = run
        p = dict(subdivision.DEFAULTS, **(params or {}))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4, S4, S4, S4)
        lay.setSpacing(S3)
        lay.addWidget(label("إفراز القطعة المحددة", "sectionTitle"))
        self.mode = ChoiceGroup([("اقتراح تلقائي", "تقسيم القطعة حسب الواجهة والمساحة الدنيا", "auto"),
                                 ("فحص قطع مرسومة", "القطع المرسومة بأداة «إفراز» على المخطط", "check")])
        if has_drawn:
            self.mode.set_value("check")
        else:
            self.mode.cards[1].setEnabled(False)
        self.mode.changed.connect(lambda _: self.recompute())
        lay.addWidget(self.mode)
        self.min_area, self.min_front = NumberEdit(), NumberEdit()
        self.min_area.set_value(p["min_area"])
        self.min_front.set_value(p["min_frontage"])
        self.road_w, self.front_d = NumberEdit(), NumberEdit()
        self.road_w.set_value(p["road_width"])
        self.front_d.set_value(p["front_depth"])
        self.internal = QCheckBox("شوارع داخلية للقطع العميقة")
        self.internal.setChecked(bool(p["internal_road"]))
        top = QHBoxLayout()
        top.addLayout(grid([Field("أقل مساحة للقطعة (م²)", self.min_area), Field("أقل واجهة (م)", self.min_front),
                            Field("عرض الشارع الداخلي (م)", self.road_w), Field("عمق الصف (م)", self.front_d)], 4), 1)
        again = button("إعادة الحساب", "secondary", "mdi6.refresh")
        again.clicked.connect(self.recompute)
        top.addWidget(again, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(top)
        lay.addWidget(self.internal)
        self.banner = Banner()
        lay.addWidget(self.banner)
        self.roads_info = label("", "caption", wrap=True)
        lay.addWidget(self.roads_info)
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
        self.apply_btn = button("عرض على المخطط واعتماد الإفراز", "success", "mdi6.check")
        self.apply_btn.clicked.connect(self._apply)
        btns.addWidget(close)
        btns.addWidget(self.apply_btn)
        lay.addLayout(btns)
        self.resize(1000, 680)
        self.result = None
        self.recompute()

    def params(self):
        return {"min_area": self.min_area.value() or 500, "min_frontage": self.min_front.value() or 18,
                "road_width": self.road_w.value() or 8, "front_depth": self.front_d.value() or 30,
                "internal_road": self.internal.isChecked()}

    def recompute(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.result = self.run(self.mode.value(), self.params())
        except ValueError as e:
            self.result = None
            self.banner.show_msg(str(e), "danger", autohide=False)
            self.apply_btn.setEnabled(False)
            return
        finally:
            QApplication.restoreOverrideCursor()
        res = self.result
        rows = lot_rows(res)
        self.table.setRowCount(len(rows))
        for i, (row, r) in enumerate(zip(rows, res["lots"])):
            for c, v in enumerate(row):
                it = QTableWidgetItem(v)
                if c == len(row) - 1:
                    it.setForeground(QColor("#2E7D32" if not r["reasons"] else "#C62828"))
                self.table.setItem(i, c, it)
        self.roads_info.setText("<br>".join(internal_lines(res)))
        self.apply_btn.setEnabled(bool(res["lots"]))
        if not res["lots"]:
            self.banner.show_msg("لم يُنتج الإفراز أي قطعة — راجع الحدود الدنيا أو اتجاه الشارع.", "warning", autohide=False)
            return
        total = sum(r["area"] for r in res["lots"])
        msg = (f"{len(res['lots'])} قطعة (مجموع {total:,.0f} م²) — مطابقة {res['ok']}"
               + (f" · مخالفة {len(res['lots']) - res['ok']}" if res["ok"] < len(res["lots"]) else ""))
        if res.get("roads_area"):
            msg += f" · الشوارع الداخلية {res['roads_area']:,.0f} م²"
        self.banner.show_msg(msg, "success" if res["ok"] == len(res["lots"]) else "warning", autohide=False)

    def _apply(self):
        if self.result:
            self.apply_requested.emit(self.result)
            self.accept()
