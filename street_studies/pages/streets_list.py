"""قائمة الشوارع المدخلة."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QTableWidget,
    QTableWidgetItem, QWidget,
)

from ..data import MIX_ON_MIX, TENDER_TYPES, format_num
from ..dialogs import ConfirmDialog, export_reports
from ..theme import C, S2, S3, S4
from ..widgets import Field, Page, StatTile, button, label

COLS = ["اسم المواطن", "المنطقة", "العطاء · الخلطة", "القطعة", "الأبعاد (م) · المساحة (م²)", "إضافات",
        "الكلفة", ""]


def num_item(text):
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return it


class StreetsListPage(Page):
    edit_requested = Signal(int)
    changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__("قائمة الشوارع", "كل السجلات المحفوظة. انقر مرتين على أي صف لتعديله.", parent)
        self.store = store

        bar = QFrame()
        bar.setObjectName("card")
        h = QHBoxLayout(bar)
        h.setContentsMargins(S4, S3, S4, S3 + 2)
        h.setSpacing(S4)
        self.f_region = QComboBox()
        self.f_tender = QComboBox()
        self.f_tender.addItem("الكل", "")
        for t in TENDER_TYPES:
            self.f_tender.addItem(t, t)
        for cb in (self.f_region, self.f_tender):
            cb.setMinimumWidth(200)
            cb.currentIndexChanged.connect(self.render)
        h.addWidget(Field("تصفية حسب المنطقة", self.f_region))
        h.addWidget(Field("طبيعة العطاء", self.f_tender))
        h.addStretch(1)
        self.count_tile = StatTile("عدد المعروض")
        self.total_tile = StatTile("الإجمالي المعروض", accent=True)
        for t in (self.count_tile, self.total_tile):
            t.setMinimumWidth(170)
            h.addWidget(t)
        self.root.addWidget(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 170)
        hh.setMinimumSectionSize(70)
        hh.setHighlightSections(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setWordWrap(False)
        self.table.cellDoubleClicked.connect(self._edit_row)
        self.root.addWidget(self.table, 1)

        self.empty = label("لا توجد شوارع مطابقة.", "muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.root.addWidget(self.empty)

    def refresh(self):
        cur = self.f_region.currentData()
        self.f_region.blockSignals(True)
        self.f_region.clear()
        self.f_region.addItem("الكل", "")
        for r in self.store.regions:
            self.f_region.addItem(r, r)
        i = self.f_region.findData(cur)
        self.f_region.setCurrentIndex(max(0, i))
        self.f_region.blockSignals(False)
        self.render()

    def render(self):
        rows = self.store.filtered(self.f_region.currentData() or "", self.f_tender.currentData() or "")
        self.table.setRowCount(len(rows))
        total = 0.0
        for r, s in enumerate(rows):
            real = self.store.streets.index(s)
            cost = self.store.street_cost(s)
            total += cost
            name = QTableWidgetItem(s.get("name", ""))
            name.setData(Qt.ItemDataRole.UserRole, real)
            f = name.font()
            f.setBold(True)
            name.setFont(f)
            if s.get("notes"):
                name.setToolTip(s["notes"])
            L, W = s.get("length") or 0, s.get("width") or 0
            mix = "على خلطة" if s.get("mixType") == MIX_ON_MIX else "على بيس كورس"
            extras = []
            if s.get("parcel"):
                extras.append("مخطط")
            if s.get("walls"):
                extras.append(f"{len(s['walls'])} جدار")
            if s.get("attachments"):
                extras.append(f"{len(s['attachments'])} مرفق")
            vals = [
                name,
                QTableWidgetItem(s.get("region") or "—"),
                QTableWidgetItem(f"{s.get('tenderType') or '—'} · {mix}"),
                QTableWidgetItem(s.get("pieceNo") or "—"),
                num_item(f"{L:g} × {W:g} = {format_num(L * W)}"),
                QTableWidgetItem(" · ".join(extras) or "—"),
                num_item(format_num(cost)),
            ]
            vals[-1].setForeground(QColor(C["success"]))
            cf = vals[-1].font()
            cf.setBold(True)
            vals[-1].setFont(cf)
            for c, it in enumerate(vals):
                self.table.setItem(r, c, it)
            actions = self._actions(real)
            self.table.setCellWidget(r, len(COLS) - 1, actions)
            # عمود الأزرار لا يُقاس تلقائياً لأن محتواه عناصر وليست نصوصاً
            last = len(COLS) - 1
            self.table.horizontalHeader().setSectionResizeMode(last, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(last, actions.sizeHint().width() + S2)
        self.count_tile.set_value(len(rows))
        self.total_tile.set_value(format_num(total))
        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)

    def _actions(self, idx):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(S2, 0, S2, 0)
        h.setSpacing(S2)
        r = button("تقرير", "secondary", "mdi6.file-pdf-box")
        e = button("", "secondary", "mdi6.pencil-outline")
        d = button("", "danger", "mdi6.trash-can-outline")
        e.setToolTip("تعديل")
        d.setToolTip("حذف")
        r.setToolTip("تصدير مجلد باسم صاحب المعاملة: تقرير PDF + Excel + ملف الأوتوكاد + المرفقات")
        for b in (r, e, d):
            b.setProperty("compact", True)
        r.clicked.connect(lambda: export_reports(self, self.store, [self.store.streets[idx]]))
        e.clicked.connect(lambda: self.edit_requested.emit(idx))
        d.clicked.connect(lambda: self.ask_delete(idx))
        h.addWidget(r)
        h.addWidget(e)
        h.addWidget(d)
        return w

    def _edit_row(self, row, _col):
        it = self.table.item(row, 0)
        if it is not None:
            self.edit_requested.emit(it.data(Qt.ItemDataRole.UserRole))

    def ask_delete(self, idx):
        s = self.store.streets[idx]
        dlg = ConfirmDialog("تأكيد الحذف", f"هل أنت متأكد من حذف سجل المواطن «{s.get('name', '')}»؟\n"
                            "لا يمكن التراجع عن هذه العملية.", parent=self.window())
        if dlg.exec():
            del self.store.streets[idx]
            self.store.save()
            self.render()
            self.changed.emit()
