"""تصدير Excel والنسخ الاحتياطي."""
import datetime
import json
import os
import shutil
import zipfile

from PySide6.QtCore import QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QMessageBox

from .. import excel_export
from ..data import TENDER_TYPES, format_num, safe_filename
from ..dialogs import export_reports
from ..theme import S2, S4
from ..widgets import Banner, Card, Field, Page, StatTile, button, grid


def _documents():
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or os.path.expanduser("~")


class ExportPage(Page):
    data_restored = Signal()

    def __init__(self, store, parent=None):
        super().__init__("تصدير Excel", "صدّر كل الشوارع أو صفِّ حسب المنطقة وطبيعة العطاء. "
                                         "الملف يحتوي معادلات تتحدّث تلقائياً عند تعديل الأسعار داخل Excel.", parent)
        self.store = store
        self.last_path = None

        card = Card("خيارات التصدير", icon_name="mdi6.filter-variant")
        self.region = QComboBox()
        self.tender = QComboBox()
        self.tender.addItem("الكل", "")
        for t in TENDER_TYPES:
            self.tender.addItem(t, t)
        for cb in (self.region, self.tender):
            cb.currentIndexChanged.connect(self.update_summary)
        card.body.addLayout(grid([Field("المنطقة", self.region), Field("طبيعة العطاء", self.tender)], 2))
        tiles = QHBoxLayout()
        tiles.setSpacing(S4)
        self.t_count = StatTile("شوارع للتصدير")
        self.t_total = StatTile("إجمالي الكلفة", accent=True)
        tiles.addWidget(self.t_count, 1)
        tiles.addWidget(self.t_total, 1)
        card.body.addLayout(tiles)
        row = QHBoxLayout()
        row.setSpacing(S2)
        self.export_btn = button("تصدير ملف Excel", "success", "mdi6.microsoft-excel")
        self.export_btn.setMinimumHeight(40)
        self.open_btn = button("فتح الملف", "secondary", "mdi6.open-in-new")
        self.folder_btn = button("فتح المجلد", "secondary", "mdi6.folder-outline")
        self.export_btn.clicked.connect(self.do_export)
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_path)))
        self.folder_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.last_path))))
        self.reports_btn = button("تقارير PDF للمعاملات المعروضة", "secondary", "mdi6.file-pdf-box")
        self.reports_btn.setToolTip("مجلد لكل معاملة باسم صاحبها: PDF + Excel + ملف الأوتوكاد + المرفقات")
        self.reports_btn.setMinimumHeight(40)
        self.reports_btn.clicked.connect(self.do_reports)
        row.addWidget(self.export_btn)
        row.addWidget(self.reports_btn)
        row.addWidget(self.open_btn)
        row.addWidget(self.folder_btn)
        row.addStretch(1)
        card.body.addLayout(row)
        self.status = Banner()
        card.body.addWidget(self.status)
        self.root.addWidget(card)

        bk = Card("النسخ الاحتياطي", f"البيانات محفوظة على هذا الجهاز في: {store.root}",
                  icon_name="mdi6.backup-restore")
        r2 = QHBoxLayout()
        r2.setSpacing(S2)
        b1 = button("حفظ نسخة احتياطية", "secondary", "mdi6.content-save-move-outline")
        b2 = button("استعادة من نسخة", "secondary", "mdi6.backup-restore")
        b1.clicked.connect(self.backup)
        b2.clicked.connect(self.restore)
        r2.addWidget(b1)
        r2.addWidget(b2)
        r2.addStretch(1)
        bk.body.addLayout(r2)
        self.bk_status = Banner()
        bk.body.addWidget(self.bk_status)
        self.root.addWidget(bk)
        self.root.addStretch(1)
        self._set_file_buttons()

    def _set_file_buttons(self):
        ok = bool(self.last_path and os.path.exists(self.last_path))
        self.open_btn.setVisible(ok)
        self.folder_btn.setVisible(ok)

    def refresh(self):
        cur = self.region.currentData()
        self.region.blockSignals(True)
        self.region.clear()
        self.region.addItem("كل المناطق", "")
        for r in self.store.regions:
            self.region.addItem(r, r)
        self.region.setCurrentIndex(max(0, self.region.findData(cur)))
        self.region.blockSignals(False)
        self.update_summary()

    def selection(self):
        fr, ft = self.region.currentData() or "", self.tender.currentData() or ""
        return fr, ft, self.store.filtered(fr, ft)

    def update_summary(self):
        _, _, rows = self.selection()
        self.t_count.set_value(len(rows))
        self.t_total.set_value(format_num(sum(self.store.street_cost(s) for s in rows)))

    def do_export(self):
        fr, ft, rows = self.selection()
        if not rows:
            self.status.show_msg("لا توجد شوارع مطابقة للتصدير.", "warning")
            return
        owners = {s.get("name", "").strip() for s in rows}
        if len(owners) == 1:  # معاملة واحدة ← الملف باسم صاحبها
            name = safe_filename(owners.pop())
        else:
            name = "دراسات_الشوارع"
            if fr:
                name += "_" + fr
            if ft:
                name += "_" + ft
        name += "_" + datetime.date.today().isoformat() + ".xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ ملف Excel", os.path.join(_documents(), name),
                                              "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            excel_export.export(self.store, rows, path, fr, ft)
        except PermissionError:
            self.status.show_msg("تعذّر حفظ الملف — قد يكون مفتوحاً في Excel. أغلقه وحاول مرة أخرى.", "danger")
            return
        except Exception as e:  # noqa: BLE001
            self.status.show_msg(f"خطأ: {e}", "danger")
            return
        self.last_path = path
        self._set_file_buttons()
        self.status.show_msg(f"تم التصدير: {os.path.basename(path)} ({len(rows)} شارع)", "success", autohide=False)

    def do_reports(self):
        _, _, rows = self.selection()
        if not rows:
            self.status.show_msg("لا توجد شوارع مطابقة للتصدير.", "warning")
            return
        export_reports(self, self.store, rows)

    def backup(self):
        name = f"نسخة_دراسات_الشوارع_{datetime.date.today().isoformat()}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ نسخة احتياطية", os.path.join(_documents(), name),
                                              "Zip (*.zip)")
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(self.store.path, "data.json")
                for fn in os.listdir(self.store.attach_dir):
                    z.write(os.path.join(self.store.attach_dir, fn), "attachments/" + fn)
        except OSError as e:
            self.bk_status.show_msg(f"تعذّر حفظ النسخة: {e}", "danger")
            return
        self.bk_status.show_msg(f"تم حفظ النسخة الاحتياطية: {os.path.basename(path)}", "success", autohide=False)

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر نسخة احتياطية", _documents(), "Zip (*.zip)")
        if not path:
            return
        try:
            with zipfile.ZipFile(path) as z:
                raw = json.loads(z.read("data.json").decode("utf-8"))
                if not isinstance(raw.get("streets"), list):
                    raise ValueError
                box = QMessageBox(QMessageBox.Icon.Warning, "استعادة نسخة احتياطية",
                                  f"سيتم استبدال كل البيانات الحالية ({len(self.store.streets)} شارع) "
                                  f"ببيانات النسخة ({len(raw['streets'])} شارع). متابعة؟",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self.window())
                box.button(QMessageBox.StandardButton.Yes).setText("استعادة")
                box.button(QMessageBox.StandardButton.No).setText("إلغاء")
                if box.exec() != QMessageBox.StandardButton.Yes:
                    return
                for info in z.infolist():
                    if info.filename.startswith("attachments/") and not info.is_dir():
                        fn = os.path.basename(info.filename)
                        with z.open(info) as src, open(os.path.join(self.store.attach_dir, fn), "wb") as dst:
                            shutil.copyfileobj(src, dst)
                with open(self.store.path, "w", encoding="utf-8") as f:
                    json.dump(raw, f, ensure_ascii=False)
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            self.bk_status.show_msg("الملف ليس نسخة احتياطية صالحة لهذا التطبيق.", "danger")
            return
        self.store.load()
        self.data_restored.emit()
        self.bk_status.show_msg(f"تمت الاستعادة — {len(self.store.streets)} شارع.", "success", autohide=False)
