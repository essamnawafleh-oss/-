"""صفحة تخصيص المظهر: الثيم، لون التمييز، الخط، حجم الخط، الزوايا."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from .. import theme
from ..theme import BUNDLED_FONTS, C, FONT_SCALES, RADII, S2, S3, S4, S6, S8, THEMES
from ..widgets import Card, ChoiceGroup, Field, button, label

ACCENTS = ["#1A5F7A", "#1F5FBF", "#0E7C66", "#2E6B3F", "#5B3FA6", "#B5367A", "#C2410C", "#9A5B1E",
           "#B07A1F", "#475569"]


def theme_preview(key, w=196, h=104):
    """رسم مصغّر للواجهة بألوان الثيم."""
    c = theme.derive(THEMES[key])
    pm = QPixmap(w * 2, h * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c["window"]))
    p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)
    # الشريط الجانبي على اليمين
    p.setBrush(QColor(c["sidebar"]))
    p.drawRoundedRect(QRectF(w - 50, 0, 50, h), 8, 8)
    p.drawRect(QRectF(w - 50, 0, 10, h))
    p.setBrush(QColor(c["sidebar_active"]))
    p.drawRoundedRect(QRectF(w - 45, 18, 40, 9), 3, 3)
    p.setBrush(QColor(c["sidebar_text"]))
    for y in (34, 46, 58):
        p.drawRoundedRect(QRectF(w - 40, y, 30, 4), 2, 2)
    # بطاقة
    p.setBrush(QColor(c["card"]))
    p.setPen(QColor(c["border"]))
    p.drawRoundedRect(QRectF(10, 12, w - 72, h - 24), 6, 6)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c["accent_fg"]))
    p.drawRoundedRect(QRectF(w - 112, 22, 40, 6), 3, 3)
    p.setBrush(QColor(c["text3"]))
    p.drawRoundedRect(QRectF(w - 132, 34, 60, 4), 2, 2)
    p.setBrush(QColor(c["input_bg"]))
    p.setPen(QColor(c["border_strong"]))
    p.drawRoundedRect(QRectF(20, 46, w - 92, 14), 3, 3)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c["accent"]))
    p.drawRoundedRect(QRectF(20, 68, 44, 14), 4, 4)
    p.setBrush(QColor(c["success"]))
    p.drawRoundedRect(QRectF(70, 68, 30, 14), 4, 4)
    p.end()
    return pm


class ThemeCard(QPushButton):
    def __init__(self, key):
        super().__init__()
        self.key = key
        self.setObjectName("themeCard")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S2, S2, S2, S2)
        lay.setSpacing(S2)
        img = QLabel()
        img.setPixmap(theme_preview(key))
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name = label(THEMES[key]["name"], "themeName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in (img, name):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(w)
        self.setFixedHeight(150)


class AppearancePage(QWidget):
    changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.settings = settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("scrollBody")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.scroll = scroll

        col = QVBoxLayout(body)
        col.setContentsMargins(S8, S6 + 4, S8, S8)
        col.setSpacing(S4)
        col.addWidget(label("المظهر", "pageTitle"))
        col.addWidget(label("خصّص ألوان التطبيق وخطوطه — تُطبَّق التغييرات فوراً وتُحفظ تلقائياً.", "pageSub"))

        # الثيم
        card = Card("الثيم", "مجموعة ألوان كاملة للواجهة (فاتحة وداكنة).", icon_name="mdi6.palette-outline")
        g = QGridLayout()
        g.setSpacing(S3)
        self.theme_cards = []
        for i, key in enumerate(THEMES):
            tc = ThemeCard(key)
            tc.setChecked(key == settings.get("theme"))
            tc.clicked.connect(lambda _=False, k=key: self.set("theme", k))
            g.addWidget(tc, i // 3, i % 3)
            self.theme_cards.append(tc)
        card.body.addLayout(g)
        col.addWidget(card)

        # لون التمييز
        card = Card("لون التمييز", "لون الأزرار والعناصر النشطة. «تلقائي» يستخدم لون الثيم.",
                    icon_name="mdi6.format-color-fill")
        row = QHBoxLayout()
        row.setSpacing(S2)
        auto = button("تلقائي", "secondary" if settings.get("accent") else None)
        auto.clicked.connect(lambda: self.set("accent", None))
        row.addWidget(auto)
        for hexc in ACCENTS:
            sw = QPushButton()
            sw.setObjectName("swatch")
            sw.setCheckable(True)
            sw.setChecked((settings.get("accent") or "").upper() == hexc)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.setToolTip(hexc)
            sw.setStyleSheet(f"QPushButton#swatch {{ background: {hexc}; }}")
            sw.clicked.connect(lambda _=False, c=hexc: self.set("accent", c))
            row.addWidget(sw)
        custom = button("لون مخصّص…", "secondary", "mdi6.eyedropper-variant")
        custom.clicked.connect(self.pick_color)
        row.addWidget(custom)
        row.addStretch(1)
        card.body.addLayout(row)
        cur = settings.get("accent")
        if cur and cur.upper() not in ACCENTS:
            card.body.addWidget(label(f"اللون الحالي المخصّص: {cur}", "caption"))
        col.addWidget(card)

        # الخط
        card = Card("الخط", "نوع الخط وحجمه في كل التطبيق وفي تقارير PDF.", icon_name="mdi6.format-font")
        self.font_combo = QComboBox()
        for title, fam, _ in BUNDLED_FONTS:
            self.font_combo.addItem(title, fam)
        system = theme.system_arabic_fonts()
        if system:
            self.font_combo.insertSeparator(self.font_combo.count())
            for fam in system:
                self.font_combo.addItem(f"{fam}  (من الجهاز)", fam)
        for i in range(self.font_combo.count()):
            fam = self.font_combo.itemData(i)
            if fam:
                f = QFont()
                f.setFamilies([fam])
                self.font_combo.setItemData(i, f, Qt.ItemDataRole.FontRole)
        i = self.font_combo.findData(settings.get("font"))
        self.font_combo.setCurrentIndex(max(0, i))
        self.font_combo.currentIndexChanged.connect(
            lambda _: self.set("font", self.font_combo.currentData()))
        card.body.addWidget(Field("نوع الخط", self.font_combo))
        card.body.addWidget(label("حجم الخط", "fieldLabel"))
        self.scale = ChoiceGroup(FONT_SCALES)
        self.scale.set_value(min((v for *_, v in FONT_SCALES), key=lambda v: abs(v - settings.get("font_scale", 1))))
        self.scale.changed.connect(lambda v: self.set("font_scale", v))
        card.body.addWidget(self.scale)
        preview = label("تقرير دراسة شارع — وادي موسى · الكلفة 19,860.00 · خلطة إسفلتية ساخنة", "preview", wrap=True)
        card.body.addWidget(preview)
        col.addWidget(card)

        # الزوايا
        card = Card("الزوايا", "استدارة زوايا البطاقات والأزرار والحقول.", icon_name="mdi6.rounded-corner")
        self.radius = ChoiceGroup(RADII)
        self.radius.set_value(min((v for *_, v in RADII), key=lambda v: abs(v - settings.get("radius", 1))))
        self.radius.changed.connect(lambda v: self.set("radius", v))
        card.body.addWidget(self.radius)
        col.addWidget(card)

        reset = button("استعادة المظهر الافتراضي", "secondary", "mdi6.restore")
        reset.clicked.connect(self.reset)
        r = QHBoxLayout()
        r.addWidget(reset)
        r.addStretch(1)
        col.addLayout(r)
        col.addStretch(1)

    def set(self, key, value):
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        self.settings.save()
        self.changed.emit()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.settings.get("accent") or C["accent"]), self.window(), "اختر لون التمييز")
        if c.isValid():
            self.set("accent", c.name().upper())

    def reset(self):
        self.settings.reset_appearance()
        self.settings.save()
        self.changed.emit()
