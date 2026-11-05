"""أسعار البنود."""
from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox,
    QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..data import UNITS, format_num
from ..theme import C, S2, S3, S4, S6
from ..widgets import Banner, Field, NumberEdit, Page, button, grid, label

# وصف نوع الرسم على المخطط لكل وحدة
UNIT_DRAW = {
    "م.ط": "يُرسم كخط — الكمية = الطول بالمتر الطولي",
    "عدد": "يُرسم كنقاط — كل نقرة = 1",
    "م²": "يُرسم كمضلع — الكمية = المساحة",
    "م³": "يُرسم كمضلع × السماكة/العمق — الكمية = الحجم",
}


class AddItemDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة بند")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S6, S6, S6, S4 + 4)
        lay.setSpacing(S3)
        lay.addWidget(label("إضافة بند جديد", "sectionTitle"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("مثال: خط مياه Ø110")
        self.group = QComboBox()
        self.group.setEditable(True)
        for g in dict.fromkeys(it["group"] for it in store.items):
            self.group.addItem(g)
        self.unit = QComboBox()
        for u in UNITS:
            self.unit.addItem(u, u)
        self.price = NumberEdit("0")
        self.depth = NumberEdit("0.30")
        self.depth.set_value(0.3)
        self.depth_field = Field("السماكة / العمق للرسم (م)", self.depth)
        lay.addWidget(Field("اسم البند *", self.name))
        lay.addLayout(grid([Field("المجموعة", self.group), Field("الوحدة", self.unit),
                            Field("سعر الوحدة", self.price)], 3))
        lay.addWidget(self.depth_field)
        self.draw_hint = Banner("", "info")
        lay.addWidget(self.draw_hint)
        self.unit.currentIndexChanged.connect(self._unit_changed)
        self._unit_changed()
        row = QHBoxLayout()
        row.setSpacing(S2)
        row.addStretch(1)
        cancel = button("إلغاء", "secondary")
        ok = button("إضافة", None, "mdi6.plus")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def _unit_changed(self):
        u = self.unit.currentData()
        self.depth_field.setVisible(u == "م³")
        self.draw_hint.show_msg("نوع الرسم على المخطط: " + UNIT_DRAW[u], "info", autohide=False)
        self.adjustSize()

    def _accept(self):
        if not self.name.text().strip():
            self.name.setProperty("error", True)
            self.name.style().polish(self.name)
            self.name.setFocus()
            return
        self.accept()

    def values(self):
        u = self.unit.currentData()
        return (self.name.text().strip(), u, self.group.currentText().strip(), self.price.value(),
                self.depth.value() if u == "م³" else None)

PRICE_COL = 4


class PriceDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        e = QLineEdit(parent)
        v = QDoubleValidator(0.0, 1e12, 3, e)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        v.setLocale(QLocale.c())
        e.setValidator(v)
        e.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        e.setStyleSheet("border-radius:0; padding:2px 8px;")
        return e

    def setEditorData(self, editor, index):
        v = index.data(Qt.ItemDataRole.UserRole) or 0
        editor.setText(f"{v:g}" if v else "")
        editor.selectAll()


class PricesPage(Page):
    changed = Signal()
    items_changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__("أسعار البنود", None, parent)
        self.store = store
        self.root.addWidget(Banner("انقر مرتين على سعر الوحدة (أو اضغط F2) لتعديله — يُحفظ فوراً وينعكس على كل الحسابات.",
                                   "info"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["الكود", "المجموعة", "اسم البند", "الوحدة", "سعر الوحدة"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setItemDelegateForColumn(PRICE_COL, PriceDelegate(self.table))
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setMinimumSectionSize(110)
        hh.setHighlightSections(False)
        self.table.itemChanged.connect(self._changed)
        bar = QHBoxLayout()
        bar.setSpacing(S2)
        add = button("إضافة بند", None, "mdi6.plus")
        add.clicked.connect(self.add_item)
        self.del_btn = button("حذف البند المضاف", "danger", "mdi6.trash-can-outline")
        self.del_btn.setToolTip("يمكن حذف البنود المضافة فقط، لا البنود الأساسية")
        self.del_btn.clicked.connect(self.delete_item)
        bar.addWidget(add)
        bar.addWidget(self.del_btn)
        bar.addStretch(1)
        self.root.addLayout(bar)
        self.root.addWidget(self.table, 1)

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.store.items))
        for r, it in enumerate(self.store.items):
            for c, v in enumerate([it["code"], it["group"], it["name"], it["unit"]]):
                cell = QTableWidgetItem(v)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    cell.setForeground(QColor(C["text2"]))
                self.table.setItem(r, c, cell)
            self.table.setItem(r, PRICE_COL, self._price_cell(it.get("price") or 0))
        self.table.blockSignals(False)

    def add_item(self):
        dlg = AddItemDialog(self.store, self.window())
        if dlg.exec():
            name, unit, group, price, depth = dlg.values()
            it = self.store.add_item(name, unit, group, price, depth)
            self.refresh()
            self.items_changed.emit()
            QMessageBox.information(self.window(), "تمت الإضافة",
                                    f"أُضيف البند «{it['name']}» ({it['code']}) بوحدة {unit}.\n"
                                    f"يظهر الآن في صفحة الإدخال، وفي المخطط ضمن نوع الرسم: {UNIT_DRAW[unit]}.")

    def delete_item(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.store.items):
            return
        it = self.store.items[row]
        if not it.get("custom"):
            QMessageBox.information(self.window(), "حذف بند", "لا يمكن حذف البنود الأساسية — يمكن حذف البنود المضافة فقط.")
            return
        used = sum(1 for s in self.store.streets if (s.get("quantities") or {}).get(it["code"]))
        msg = f"حذف البند «{it['name']}»؟"
        if used:
            msg += f"\n\nهذا البند مستخدم في {used} سجل — لن تُحتسب كميته بعد الحذف."
        if QMessageBox.question(self.window(), "حذف بند", msg) == QMessageBox.StandardButton.Yes:
            self.store.remove_item(it["code"])
            self.refresh()
            self.items_changed.emit()

    def _price_cell(self, v):
        cell = QTableWidgetItem(format_num(v))
        cell.setData(Qt.ItemDataRole.UserRole, float(v))
        cell.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        cell.setBackground(QColor("#FFF9E6"))
        f = cell.font()
        f.setBold(True)
        cell.setFont(f)
        cell.setToolTip("انقر مرتين للتعديل")
        return cell

    def _changed(self, cell):
        if cell.column() != PRICE_COL:
            return
        raw = cell.text().replace(",", "").strip()
        try:
            v = float(raw) if raw else 0.0
        except ValueError:
            v = cell.data(Qt.ItemDataRole.UserRole) or 0.0
        self.store.items[cell.row()]["price"] = v
        self.store.save()
        self.table.blockSignals(True)
        cell.setText(format_num(v))
        cell.setData(Qt.ItemDataRole.UserRole, v)
        self.table.blockSignals(False)
        self.changed.emit()
