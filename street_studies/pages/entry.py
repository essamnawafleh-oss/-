"""صفحة إدخال بيانات الشارع."""
import copy
import os

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
)

from .. import data, dxf_render
from ..data import (
    CAD_EXTS, MIX_ON_BASE, MIX_ON_MIX, REINFORCED_TABLE, WALL_REINFORCED_CODE, WALL_RUBBLE_CODE,
    calc_reinforced, calc_rubble, format_file_size, format_num, resource_path,
)
from ..dialogs import ImageDialog
from ..theme import C, S1, S2, S3, S4, S6, S8
from ..widgets import (
    Banner, Card, ChoiceGroup, Field, NumberEdit, button, grid, icon, label, repolish,
)

AUTO_CODES = ("RD-001", "RD-004", "ASP-002")
WALL_CODES = (WALL_RUBBLE_CODE, WALL_REINFORCED_CODE)


class WallWidget(QFrame):
    changed = Signal()
    removed = Signal(object)

    def __init__(self, wall, number, parent=None):
        super().__init__(parent)
        self.setObjectName("subCard")
        self.wall = wall
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4, S3, S4, S3 + 2)
        lay.setSpacing(S3)

        head = QHBoxLayout()
        reinforced = wall["type"] == "reinforced"
        ic = QLabel()
        ic.setPixmap(icon("mdi6.wall" if reinforced else "mdi6.wall-sconce-flat-outline",
                          C["accent_fg"]).pixmap(18, 18))
        head.addWidget(ic)
        self.title = label("", "subTitle")
        head.addWidget(self.title, 1)
        rm = button("حذف", "danger", "mdi6.trash-can-outline")
        rm.clicked.connect(lambda: self.removed.emit(self.wall))
        head.addWidget(rm)
        lay.addLayout(head)
        self.set_number(number)

        if reinforced:
            self.h = QComboBox()
            for r in REINFORCED_TABLE:
                self.h.addItem(f"{r['H']} سم", r["H"])
            self.h.setCurrentIndex(max(0, self.h.findData(wall.get("h") or 150)))
            self.length = NumberEdit()
            self.length.set_value(wall.get("length") or None)
            self.h.currentIndexChanged.connect(self._read)
            self.length.textChanged.connect(self._read)
            lay.addLayout(grid([Field("الارتفاع H", self.h), Field("الطول (م)", self.length), QWidget()], 3))
        else:
            self.L, self.H, self.hb = NumberEdit(), NumberEdit(), NumberEdit()
            self.L.set_value(wall.get("L") or None)
            self.H.set_value(wall.get("H") or None)
            self.hb.set_value(wall.get("hb") or None)
            for w in (self.L, self.H, self.hb):
                w.textChanged.connect(self._read)
            lay.addLayout(grid([Field("الطول L (م)", self.L), Field("ارتفاع الجدار H (م)", self.H),
                                Field("ارتفاع القاعدة hb (م)", self.hb)], 3))

        self.result = label("", "wallResult", wrap=True)
        lay.addWidget(self.result)
        self._update_result()

    def set_number(self, n):
        kind = "جدار مسلح" if self.wall["type"] == "reinforced" else "جدار دبش وباطون"
        self.title.setText(f"{kind} #{n}")

    def _read(self):
        if self.wall["type"] == "reinforced":
            self.wall["h"] = self.h.currentData()
            self.wall["length"] = self.length.value()
        else:
            self.wall["L"], self.wall["H"], self.wall["hb"] = self.L.value(), self.H.value(), self.hb.value()
        self._update_result()
        self.changed.emit()

    def _update_result(self):
        w = self.wall
        if w["type"] == "reinforced":
            r = calc_reinforced(w.get("h") or 150, w.get("length") or 0)
            txt = (f"خرسانة: <b>{r['total_conc']:.2f} م³</b>   ·   حديد: <b>{r['total_steel']:.1f} كجم</b>"
                   if r else "")
        else:
            r = calc_rubble(w.get("L") or 0, w.get("H") or 0, w.get("hb") or 0)
            txt = (f"حجم كلي: <b>{r['v_total']:.3f} م³</b>   (جدار: {r['v_wall']:.3f} + قاعدة: {r['v_base']:.3f})"
                   if r else "")
        self.result.setText(txt)
        self.result.setVisible(bool(txt))


class AttachmentCard(QFrame):
    removed = Signal(object)

    def __init__(self, att, path, parent=None):
        super().__init__(parent)
        self.setObjectName("attachCard")
        self.att, self.path = att, path
        self.setFixedWidth(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S2, S2, S2, S2)
        lay.setSpacing(S1)
        thumb = QLabel()
        thumb.setObjectName("thumb")
        thumb.setFixedHeight(96)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(path) if att.get("isImage") else QPixmap()
        if not pm.isNull():
            thumb.setPixmap(pm.scaled(QSize(134, 96), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation).copy(0, 0, 134, 96))
        else:
            thumb.setPixmap(icon("mdi6.file-document-outline", C["accent_fg"]).pixmap(36, 36))
        lay.addWidget(thumb)
        name = label(att["name"], "caption")
        name.setToolTip(att["name"])
        fm = name.fontMetrics()
        name.setText(fm.elidedText(att["name"], Qt.TextElideMode.ElideMiddle, 134))
        lay.addWidget(name)
        lay.addWidget(label(format_file_size(att.get("size")), "muted"))
        rm = button("", "iconRemove", "mdi6.close", C["danger"])
        rm.setToolTip("حذف المرفق")
        rm.setParent(self)
        rm.move(6, 6)
        rm.clicked.connect(lambda: self.removed.emit(self.att))
        self.setToolTip("انقر للعرض" if att.get("isImage") else "انقر لفتح الملف")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.att.get("isImage"):
                ImageDialog(self.att["name"], self.path, self.window()).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))
        super().mouseReleaseEvent(e)


class EntryPage(QWidget):
    saved = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.store = store
        self.edit_index = -1
        self.walls = []
        self.wall_seq = 0
        self.attachments = []
        self.parcel = None
        self.manual = set()
        self.qty = {}
        self._building = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("scrollBody")
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)
        outer.addWidget(self._action_bar())

        col = QVBoxLayout(body)
        col.setContentsMargins(S8, S6 + 4, S8, S8)
        col.setSpacing(S4)
        self.title = label("إدخال بيانات شارع", "pageTitle")
        col.addWidget(self.title)
        col.addWidget(label("ابدأ باختيار المنطقة وطبيعة العطاء، ثم أدخل اسم المواطن وبيانات الشارع. "
                            "الكميات ذات الخلفية الخضراء تُحسب تلقائياً ويمكن تعديلها يدوياً.", "pageSub", wrap=True))
        self.banner = Banner()
        col.addWidget(self.banner)

        col.addWidget(self._region_card())
        col.addWidget(self._street_card())
        col.addWidget(self._parcel_card())
        col.addWidget(self._mix_card())
        for group in self._groups():
            col.addWidget(self._qty_card(group))
        col.addWidget(self._walls_card())
        col.addWidget(self._attach_card())
        col.addStretch(1)

        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save)
        self.clear_form()

    # ---------- بناء الأقسام ----------
    def _region_card(self):
        card = Card("المنطقة وطبيعة العطاء", step=1)
        self.region = QComboBox()
        self.new_region = QLineEdit()
        self.new_region.setPlaceholderText("اسم منطقة جديدة")
        add = button("إضافة", "secondary", "mdi6.plus")
        add.clicked.connect(self.add_region)
        self.new_region.returnPressed.connect(self.add_region)
        nr = QWidget()
        h = QHBoxLayout(nr)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(S2)
        h.addWidget(self.new_region, 1)
        h.addWidget(add)
        card.body.addLayout(grid([Field("المنطقة *", self.region), Field("إضافة منطقة جديدة", nr)], 2))
        card.body.addSpacing(S1)
        card.body.addWidget(label("طبيعة العطاء", "fieldLabel"))
        self.tender = ChoiceGroup([("خلطات", "أعمال إسفلت وطرق", "خلطات"),
                                   ("تصريف", "تصريف مياه الأمطار", "تصريف")])
        card.body.addWidget(self.tender)
        return card

    def _street_card(self):
        card = Card("بيانات المواطن والشارع", step=2)
        self.name = QLineEdit()
        self.name.setPlaceholderText("مثال: أحمد محمد")
        self.piece = QLineEdit()
        self.piece.setPlaceholderText("مثال: 12")
        self.length = NumberEdit()
        self.width = NumberEdit()
        self.area = QLineEdit()
        self.area.setReadOnly(True)
        self.area.setPlaceholderText("تُحسب تلقائياً")
        self.area.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.area.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("أي ملاحظات…")
        self.notes.setFixedHeight(self.notes.fontMetrics().lineSpacing() * 3 + 22)
        card.body.addLayout(grid([Field("اسم المواطن *", self.name), Field("رقم القطعة", self.piece),
                                  QWidget()], 3))
        card.body.addLayout(grid([Field("الطول (م) *", self.length), Field("العرض (م) *", self.width),
                                  Field("مساحة الطريق (م²)", self.area)], 3))
        card.body.addWidget(Field("ملاحظات", self.notes))
        for w in (self.length, self.width):
            w.textChanged.connect(self.update_auto)
        for w in (self.name, self.length, self.width):
            w.textEdited.connect(lambda _=None, w=w: self._set_error(w, False))
        return card

    def _mix_card(self):
        card = Card("نوع الخلطة الساخنة", step=3)
        self.mix = ChoiceGroup([("خلطة على بيس كورس", "تسوية + بيس كورس + خلطة", MIX_ON_BASE),
                                ("خلطة على خلطة", "التسوية والبيس كورس = صفر", MIX_ON_MIX)])
        self.mix.changed.connect(lambda _: self.update_auto())
        card.body.addWidget(self.mix)
        return card

    def _groups(self):
        groups = {}
        for it in self.store.items:
            if it["code"] in WALL_CODES:
                continue
            groups.setdefault(it["group"], []).append(it)
        return list(groups.items())

    def _qty_card(self, group):
        name, items = group
        card = Card(name, "الكميات بالوحدة المذكورة بجانب كل بند", icon_name="mdi6.package-variant-closed")
        fields = []
        for it in items:
            e = NumberEdit()
            auto = bool(it.get("auto"))
            if auto:
                e.setProperty("auto", True)
                e.textEdited.connect(lambda _=None, c=it["code"]: self.manual.add(c))
            e.textChanged.connect(self.update_live_cost)
            self.qty[it["code"]] = e
            fields.append(Field(f"{it['name']} ({it['unit']})", e, "تلقائي" if auto else None))
        card.body.addLayout(grid(fields, 4))
        return card

    def _walls_card(self):
        card = Card("الجدران", "يمكن إضافة أكثر من جدار. الكميات تُضاف تلقائياً إلى بنود «جدران مسلحة» و«جدران دبش وباطون».",
                    icon_name="mdi6.wall")
        self.walls_box = QVBoxLayout()
        self.walls_box.setSpacing(S3)
        card.body.addLayout(self.walls_box)
        self.walls_empty = label("لا توجد جدران مضافة بعد.", "muted")
        card.body.addWidget(self.walls_empty)
        row = QHBoxLayout()
        row.setSpacing(S2)
        a1 = button("جدار مسلح", "secondary", "mdi6.plus")
        a2 = button("جدار دبش وباطون", "secondary", "mdi6.plus")
        d1 = button("مخطط الجدار المسلح", "ghost", "mdi6.ruler-square", C["accent_fg"])
        d2 = button("مخطط جدار الدبش", "ghost", "mdi6.ruler-square", C["accent_fg"])
        a1.clicked.connect(lambda: self.add_wall("reinforced"))
        a2.clicked.connect(lambda: self.add_wall("rubble"))
        d1.clicked.connect(lambda: ImageDialog("مخطط الجدار المسلح",
                                               resource_path("diagram_reinforced.png"), self.window()).exec())
        d2.clicked.connect(lambda: ImageDialog("مخطط جدار دبش وباطون",
                                               resource_path("diagram_rubble.png"), self.window()).exec())
        for b in (a1, a2):
            row.addWidget(b)
        row.addStretch(1)
        for b in (d1, d2):
            row.addWidget(b)
        card.body.addLayout(row)
        return card

    def _parcel_card(self):
        card = Card("ملف قطعة الأرض (أوتوكاد)",
                    "أرفق ملف DXF للقطعة — يظهر المخطط هنا وفي تقرير PDF، ويُصدَّر الملف مع التقرير باسم صاحب المعاملة.",
                    icon_name="mdi6.vector-square")
        # الحالة الفارغة
        self.parcel_empty = QFrame()
        self.parcel_empty.setObjectName("dropZone")
        ev = QVBoxLayout(self.parcel_empty)
        ev.setContentsMargins(S4, S6, S4, S6)
        ev.setSpacing(S2)
        ic = QLabel()
        ic.setPixmap(icon("mdi6.file-cad", C["accent_fg"]).pixmap(36, 36))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(ic)
        t = label("اسحب ملف DXF إلى هنا أو اختره من جهازك", "caption")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(t)
        pick = button("إرفاق ملف DXF", None, "mdi6.paperclip")
        pick.clicked.connect(self.pick_parcel)
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(pick)
        r.addStretch(1)
        ev.addLayout(r)
        card.body.addWidget(self.parcel_empty)

        # الحالة مع ملف
        self.parcel_box = QWidget()
        h = QHBoxLayout(self.parcel_box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(S4)
        self.parcel_preview = QLabel()
        self.parcel_preview.setObjectName("cadPreview")
        self.parcel_preview.setFixedSize(380, 240)
        self.parcel_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.parcel_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.parcel_preview.setToolTip("انقر لعرض المخطط بحجم كبير")
        self.parcel_preview.mouseReleaseEvent = lambda e: self.view_parcel()
        h.addWidget(self.parcel_preview)
        info = QVBoxLayout()
        info.setSpacing(S2)
        self.parcel_name = label("", "subTitle", wrap=True)
        self.parcel_meta = label("", "caption", wrap=True)
        info.addWidget(self.parcel_name)
        info.addWidget(self.parcel_meta)
        info.addStretch(1)
        btns = QGridLayout()
        btns.setSpacing(S2)
        b_view = button("عرض المخطط", "secondary", "mdi6.magnify-plus-outline")
        b_open = button("فتح في أوتوكاد", "secondary", "mdi6.open-in-new")
        b_swap = button("استبدال الملف", "secondary", "mdi6.swap-horizontal")
        b_rm = button("إزالة", "danger", "mdi6.trash-can-outline")
        b_view.clicked.connect(self.view_parcel)
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.store.attachment_path(self.parcel))))
        b_swap.clicked.connect(self.pick_parcel)
        b_rm.clicked.connect(lambda: self.set_parcel(None))
        for i, b in enumerate((b_view, b_open, b_swap, b_rm)):
            btns.addWidget(b, i // 2, i % 2)
        info.addLayout(btns)
        h.addLayout(info, 1)
        card.body.addWidget(self.parcel_box)
        self.setAcceptDrops(True)
        return card

    def _attach_card(self):
        card = Card("الصور والمرفقات", "مخططات، بروفايلات، PDF … بدون حد لحجم الملفات. يمكنك أيضاً سحب الملفات وإفلاتها هنا.",
                    icon_name="mdi6.paperclip")
        row = QHBoxLayout()
        row.setSpacing(S2)
        b1 = button("إضافة صور", "secondary", "mdi6.image-plus-outline")
        b2 = button("إضافة مرفقات", "secondary", "mdi6.file-plus-outline")
        b1.clicked.connect(lambda: self.pick_files(True))
        b2.clicked.connect(lambda: self.pick_files(False))
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        card.body.addLayout(row)
        self.attach_grid = QGridLayout()
        self.attach_grid.setSpacing(S3)
        self.attach_grid.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        card.body.addLayout(self.attach_grid)
        self.attach_empty = label("لا توجد مرفقات بعد.", "muted")
        card.body.addWidget(self.attach_empty)
        return card

    def _action_bar(self):
        bar = QFrame()
        bar.setObjectName("actionBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(S8, S3, S8, S3)
        h.setSpacing(S3)
        self.save_btn = button("حفظ والانتقال للتالي", None, "mdi6.content-save-outline")
        self.save_btn.setToolTip("Ctrl+S")
        self.save_btn.clicked.connect(self.save)
        clear = button("مسح النموذج", "secondary", "mdi6.eraser")
        clear.clicked.connect(self.clear_form)
        h.addWidget(self.save_btn)
        h.addWidget(clear)
        h.addStretch(1)

        cost = QFrame()
        cost.setObjectName("liveCost")
        cl = QHBoxLayout(cost)
        cl.setContentsMargins(S4, S2, S4, S2)
        cl.setSpacing(S3)
        txt = QVBoxLayout()
        txt.setSpacing(0)
        txt.addWidget(label("كلفة هذا الشارع", "liveCostLabel"))
        self.cost_note = label("لم تُدخل أسعار البنود — اذهب إلى صفحة الأسعار", "liveCostNote")
        txt.addWidget(self.cost_note)
        cl.addLayout(txt)
        self.cost_value = label("0.00", "liveCostValue")
        cl.addWidget(self.cost_value)
        h.addWidget(cost)
        return bar

    # ---------- المنطق ----------
    def refresh(self):
        """يُستدعى عند فتح الصفحة (بعد تغيير الأسعار مثلاً)."""
        self.fill_regions()
        self.update_live_cost()

    def fill_regions(self, select=None):
        cur = select or self.region.currentText()
        self.region.blockSignals(True)
        self.region.clear()
        self.region.addItems(self.store.regions)
        i = self.region.findText(cur)
        if i >= 0:
            self.region.setCurrentIndex(i)
        self.region.blockSignals(False)

    def add_region(self):
        name = self.new_region.text().strip()
        if not name:
            self.banner.show_msg("أدخل اسم المنطقة", "warning")
            return
        if name in self.store.regions:
            self.banner.show_msg("المنطقة موجودة مسبقاً", "warning")
            return
        self.store.regions.append(name)
        self.store.save()
        self.fill_regions(select=name)
        self.new_region.clear()
        self.banner.show_msg(f"تمت إضافة المنطقة: {name}", "success")

    def update_auto(self):
        l, w = self.length.value(), self.width.value()
        self.area.setText(f"{l * w:.2f}" if (l and w) else "")
        auto = data.auto_quantities(l, w, self.mix.value())
        for code, v in auto.items():
            e = self.qty.get(code)
            if e is not None and code not in self.manual:
                e.blockSignals(True)
                e.set_value(v, 2) if v is not None else e.setText("")
                e.blockSignals(False)
        self.update_live_cost()

    def wall_quantities(self):
        rubble, reinforced = data.wall_totals(self.walls)
        return {WALL_RUBBLE_CODE: round(rubble, 3), WALL_REINFORCED_CODE: round(reinforced, 3)}

    def quantities(self):
        q = {code: e.value() for code, e in self.qty.items() if e.value() > 0}
        q.update({c: v for c, v in self.wall_quantities().items() if v > 0})
        return q

    def update_live_cost(self):
        q = self.quantities()
        total = sum(v * self.store.price(c) for c, v in q.items())
        has_price = any(self.store.price(c) > 0 for c in q)
        self.cost_value.setText(format_num(total))
        self.cost_note.setVisible(bool(q) and not has_price)

    # الجدران
    def add_wall(self, kind):
        self.wall_seq += 1
        w = ({"id": self.wall_seq, "type": "reinforced", "h": 150, "length": 0} if kind == "reinforced"
             else {"id": self.wall_seq, "type": "rubble", "L": 0, "H": 0, "hb": 0.3})
        self.walls.append(w)
        self.render_walls()

    def remove_wall(self, wall):
        self.walls = [w for w in self.walls if w is not wall]
        self.render_walls()

    def render_walls(self):
        while self.walls_box.count():
            it = self.walls_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for i, w in enumerate(self.walls):
            ww = WallWidget(w, i + 1)
            ww.changed.connect(self.update_live_cost)
            ww.removed.connect(self.remove_wall)
            self.walls_box.addWidget(ww)
        self.walls_empty.setVisible(not self.walls)
        self.update_live_cost()

    # المرفقات
    def pick_files(self, images):
        flt = ("الصور (*.png *.jpg *.jpeg *.webp *.bmp *.gif)" if images else
               "ملفات (*.pdf *.doc *.docx *.xls *.xlsx *.dwg *.dxf *.zip *.png *.jpg *.jpeg *.webp);;كل الملفات (*)")
        paths, _ = QFileDialog.getOpenFileNames(self, "اختر ملفات", os.path.expanduser("~"), flt)
        self.add_files(paths)

    def add_files(self, paths):
        for p in paths:
            try:
                self.attachments.append(self.store.add_attachment(p))
            except OSError as e:
                self.banner.show_msg(f"تعذر قراءة الملف: {os.path.basename(p)} ({e})", "warning")
        self.render_attachments()

    # ملف القطعة
    def pick_parcel(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف قطعة الأرض", os.path.expanduser("~"),
                                              "ملفات أوتوكاد (*.dxf *.dwg);;DXF (*.dxf)")
        if path:
            self.attach_parcel(path)

    def attach_parcel(self, path):
        try:
            self.set_parcel(self.store.add_attachment(path))
        except OSError as e:
            self.banner.show_msg(f"تعذر قراءة الملف: {e}", "warning")
            return
        if path.lower().endswith(".dwg"):
            self.banner.show_msg("تم إرفاق ملف DWG — سيُصدَّر مع التقرير، لكن المعاينة متاحة لملفات DXF فقط. "
                                 "(من أوتوكاد: Save As ← DXF)", "info", autohide=True)

    def set_parcel(self, parcel):
        self.parcel = parcel
        self.render_parcel()

    def render_parcel(self):
        has = bool(self.parcel)
        self.parcel_empty.setVisible(not has)
        self.parcel_box.setVisible(has)
        if not has:
            return
        p = self.parcel
        path = self.store.attachment_path(p)
        self.parcel_name.setText(p["name"])
        meta = [format_file_size(p.get("size"))]
        if p["name"].lower().endswith(".dxf"):
            try:
                d = dxf_render.load(path)
                img = dxf_render.render(d, 760, 480, line_width=1.4)
                pm = QPixmap.fromImage(img).scaled(QSize(378, 238), Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)
                self.parcel_preview.setPixmap(pm)
                meta.append(f"أبعاد الرسم: {dxf_render.size_text(d)}")
                area = dxf_render.area_of_largest_closed(d)
                if area:
                    meta.append(f"مساحة أكبر شكل مغلق: {format_num(area)}")
                meta.append(f"{d.entities:,} عنصر")
            except ValueError as e:
                self.parcel_preview.setPixmap(icon("mdi6.file-alert-outline", C["warning"]).pixmap(48, 48))
                meta.append(str(e))
        else:
            self.parcel_preview.setPixmap(icon("mdi6.file-cad", C["accent_fg"]).pixmap(56, 56))
            meta.append("المعاينة متاحة لملفات DXF فقط")
        self.parcel_meta.setText("<br>".join(meta))

    def view_parcel(self):
        if not self.parcel or not self.parcel["name"].lower().endswith(".dxf"):
            return
        img, err = dxf_render.render_file(self.store.attachment_path(self.parcel), 2400, 1600, line_width=1.6)
        if img is not None:
            ImageDialog(f"مخطط القطعة — {self.parcel['name']}", QPixmap.fromImage(img), self.window()).exec()

    # السحب والإفلات: ملفات أوتوكاد ← ملف القطعة، والباقي ← المرفقات
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile() and os.path.isfile(u.toLocalFile())]
        cad = [p for p in paths if os.path.splitext(p)[1].lower() in CAD_EXTS]
        if cad:
            self.attach_parcel(cad[0])
        self.add_files([p for p in paths if p not in cad[:1]])
        e.acceptProposedAction()

    def remove_attachment(self, att):
        self.attachments = [a for a in self.attachments if a is not att]
        self.render_attachments()

    def render_attachments(self):
        while self.attach_grid.count():
            it = self.attach_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for i, a in enumerate(self.attachments):
            c = AttachmentCard(a, self.store.attachment_path(a))
            c.removed.connect(self.remove_attachment)
            self.attach_grid.addWidget(c, i // 5, i % 5)
        self.attach_empty.setVisible(not self.attachments)

    # النموذج
    def _set_error(self, w, on):
        w.setProperty("error", on)
        repolish(w)

    def clear_form(self):
        self.edit_index = -1
        self.title.setText("إدخال بيانات شارع")
        self.save_btn.setText("حفظ والانتقال للتالي")
        for w in (self.name, self.piece, self.length, self.width, self.area):
            w.clear()
            self._set_error(w, False)
        self.notes.clear()
        self.tender.set_value("خلطات")
        self.mix.set_value(MIX_ON_BASE)
        self.manual.clear()
        for e in self.qty.values():
            e.blockSignals(True)
            e.clear()
            e.blockSignals(False)
        self.walls = []
        self.render_walls()
        self.attachments = []
        self.render_attachments()
        self.set_parcel(None)
        self.fill_regions()
        self.update_auto()

    def collect(self):
        return {
            "name": self.name.text().strip(),
            "pieceNo": self.piece.text().strip(),
            "region": self.region.currentText(),
            "tenderType": self.tender.value(),
            "mixType": self.mix.value(),
            "length": self.length.value(),
            "width": self.width.value(),
            "notes": self.notes.toPlainText().strip(),
            "quantities": self.quantities(),
            "walls": copy.deepcopy(self.walls),
            "attachments": copy.deepcopy(self.attachments),
            "parcel": copy.deepcopy(self.parcel),
        }

    def snapshot(self):
        """حالة النموذج الحالية (تُستخدم لإعادة بناء الواجهة عند تغيير المظهر دون فقدان الإدخال)."""
        return self.collect(), self.edit_index, self.scroll.verticalScrollBar().value()

    def restore(self, snap):
        street, idx, scroll = snap
        self.load_street(street, idx)
        if idx < 0:
            self.title.setText("إدخال بيانات شارع")
            self.save_btn.setText("حفظ والانتقال للتالي")
        self.scroll.verticalScrollBar().setValue(scroll)

    def save(self):
        name = self.name.text().strip()
        problems = []
        if not name:
            problems.append((self.name, "اسم المواطن مطلوب"))
        if self.length.value() <= 0:
            problems.append((self.length, "أدخل الطول بشكل صحيح"))
        if self.width.value() <= 0:
            problems.append((self.width, "أدخل العرض بشكل صحيح"))
        if not self.region.currentText():
            problems.append((self.region, "اختر المنطقة"))
        if problems:
            for w, _ in problems:
                self._set_error(w, True)
            self.banner.show_msg(" · ".join(m for _, m in problems), "warning")
            problems[0][0].setFocus()
            self.scroll.verticalScrollBar().setValue(0)
            return

        street = self.collect()
        updating = self.edit_index >= 0
        if updating:
            self.store.streets[self.edit_index] = street
        else:
            self.store.streets.append(street)
        self.store.save()
        cost = self.store.street_cost(street)
        self.clear_form()
        self.saved.emit()
        self.banner.show_msg(f"{'تم تحديث السجل' if updating else 'تم حفظ السجل'} — «{name}» — الكلفة: "
                             f"{format_num(cost)} — المنطقة: {street['region']} — العطاء: {street['tenderType']}",
                             "success")
        self.scroll.verticalScrollBar().setValue(0)
        self.name.setFocus()

    def edit_street(self, idx):
        self.load_street(self.store.streets[idx], idx)

    def load_street(self, s, idx):
        self.clear_form()
        self.edit_index = idx
        self.title.setText(f"تعديل سجل: {s.get('name', '')}")
        self.save_btn.setText("تحديث السجل")
        self.name.setText(s.get("name", ""))
        self.piece.setText(s.get("pieceNo", ""))
        self.notes.setPlainText(s.get("notes", ""))
        self.fill_regions(select=s.get("region"))
        self.tender.set_value(s.get("tenderType") or "خلطات")
        self.mix.set_value(s.get("mixType") or MIX_ON_BASE)
        q = s.get("quantities") or {}
        # البند التلقائي يُعتبر يدوياً فقط إذا اختلفت قيمته المحفوظة عن المحسوبة
        auto = data.auto_quantities(s.get("length") or 0, s.get("width") or 0, s.get("mixType"))
        for code, e in self.qty.items():
            v = q.get(code)
            e.blockSignals(True)
            e.set_value(v)
            e.blockSignals(False)
            if code in AUTO_CODES and v is not None and abs((auto.get(code) or 0) - v) > 0.005:
                self.manual.add(code)
        self.walls = copy.deepcopy(s.get("walls") or [])
        self.wall_seq = max([w.get("id", 0) for w in self.walls] + [0])
        self.render_walls()
        self.attachments = copy.deepcopy(s.get("attachments") or [])
        self.render_attachments()
        self.set_parcel(copy.deepcopy(s.get("parcel")))
        self.length.blockSignals(True)
        self.width.blockSignals(True)
        self.length.set_value(s.get("length") or None)
        self.width.set_value(s.get("width") or None)
        self.length.blockSignals(False)
        self.width.blockSignals(False)
        self.update_auto()
        self.scroll.verticalScrollBar().setValue(0)
