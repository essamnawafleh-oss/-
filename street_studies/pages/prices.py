"""أسعار البنود."""
from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLineEdit, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
)

from ..data import format_num
from ..theme import C
from ..widgets import Banner, Page

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
