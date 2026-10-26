"""الملخص والتقارير."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem,
)

from ..data import format_num
from ..theme import S3, S4
from ..widgets import Page, StatTile, label


def make_table(headers, stretch_col):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(34)
    t.setShowGrid(False)
    hh = t.horizontalHeader()
    hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    hh.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    hh.setMinimumSectionSize(110)
    hh.setHighlightSections(False)
    return t


def num(text):
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return it


class SummaryPage(Page):
    def __init__(self, store, parent=None):
        super().__init__("الملخص والتقارير", "إجماليات كل الشوارع المحفوظة حسب الأسعار الحالية.", parent)
        self.store = store
        tiles = QHBoxLayout()
        tiles.setSpacing(S4)
        self.t_count = StatTile("عدد الشوارع")
        self.t_total = StatTile("إجمالي الكلفة", accent=True)
        self.t_items = StatTile("عدد البنود")
        for t in (self.t_count, self.t_total, self.t_items):
            tiles.addWidget(t, 1)
        self.root.addLayout(tiles)

        self.root.addWidget(label("إجمالي الكلفة حسب المجموعة", "sectionTitle"))
        self.groups = make_table(["المجموعة", "إجمالي الكلفة"], 0)
        self.root.addWidget(self.groups)
        self.root.addSpacing(S3)
        self.root.addWidget(label("تفصيل حسب البند", "sectionTitle"))
        self.items = make_table(["الكود", "المجموعة", "اسم البند", "الوحدة", "إجمالي الكمية", "إجمالي الكلفة"], 2)
        self.root.addWidget(self.items, 1)

    def refresh(self):
        st = self.store
        total = sum(st.street_cost(s) for s in st.streets)
        self.t_count.set_value(len(st.streets))
        self.t_total.set_value(format_num(total))
        self.t_items.set_value(len(st.items))

        groups = {}
        for it in st.items:
            groups.setdefault(it["group"], 0.0)
        for s in st.streets:
            for code, q in (s.get("quantities") or {}).items():
                it = st.item(code)
                if it:
                    groups[it["group"]] += float(q or 0) * float(it.get("price") or 0)
        self.groups.setRowCount(len(groups))
        for r, (g, v) in enumerate(groups.items()):
            self.groups.setItem(r, 0, QTableWidgetItem(g))
            self.groups.setItem(r, 1, num(format_num(v)))
        self.groups.setFixedHeight(self.groups.horizontalHeader().height() + 34 * len(groups) + 4)

        self.items.setRowCount(len(st.items))
        for r, it in enumerate(st.items):
            qty = sum(float((s.get("quantities") or {}).get(it["code"]) or 0) for s in st.streets)
            cost = qty * float(it.get("price") or 0)
            for c, v in enumerate([it["code"], it["group"], it["name"], it["unit"]]):
                self.items.setItem(r, c, QTableWidgetItem(v))
            self.items.setItem(r, 4, num(format_num(qty) if qty else "—"))
            self.items.setItem(r, 5, num(format_num(cost) if cost else "—"))
