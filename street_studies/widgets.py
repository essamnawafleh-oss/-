"""عناصر واجهة مشتركة بين الصفحات."""
import qtawesome as qta
from PySide6.QtCore import QLocale, Qt, QTimer, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from .theme import C, S1, S2, S3, S4, S6, S8


def icon(name, color=None):
    return qta.icon(name, color=color or C["text2"])


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def button(text, kind=None, icon_name=None, icon_color=None):
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if icon_name:
        default = {None: C["on_accent"], "success": C["on_success"], "dangerSolid": C["on_danger"],
                   "danger": C["danger"]}.get(kind, C["text2"])
        b.setIcon(icon(icon_name, icon_color or default))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def label(text, obj=None, wrap=False):
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def divider():
    d = QFrame()
    d.setObjectName("divider")
    return d


class Card(QFrame):
    """بطاقة بيضاء بعنوان اختياري."""

    def __init__(self, title=None, subtitle=None, step=None, icon_name=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(S6, S4 + 2, S6, S6)
        self.outer.setSpacing(S4)
        if title:
            head = QHBoxLayout()
            head.setSpacing(S3)
            if step is not None:
                head.addWidget(label(str(step), "stepNum"))
            elif icon_name:
                ic = QLabel()
                ic.setPixmap(icon(icon_name, C["accent"]).pixmap(20, 20))
                head.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(title, "sectionTitle"))
            if subtitle:
                col.addWidget(label(subtitle, "sectionSub", wrap=True))
            head.addLayout(col, 1)
            self.head = head
            self.outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(S3)
        self.outer.addLayout(self.body)


class Field(QWidget):
    """تسمية فوق الحقل."""

    def __init__(self, text, widget, tag=None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(S1 + 2)
        row = QHBoxLayout()
        row.setSpacing(S2)
        self.label = label(text, "fieldLabel")
        row.addWidget(self.label)
        if tag:
            row.addWidget(label(tag, "autoTag"))
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(widget)
        self.widget = widget


def grid(widgets, cols=3, spacing=S4):
    g = QGridLayout()
    g.setHorizontalSpacing(spacing)
    g.setVerticalSpacing(S3)
    for i, w in enumerate(widgets):
        g.addWidget(w, i // cols, i % cols)
    for c in range(cols):
        g.setColumnStretch(c, 1)
    return g


class NumberEdit(QLineEdit):
    """حقل رقمي (أرقام إنجليزية، اتجاه من اليسار لليمين)."""

    def __init__(self, placeholder="0", parent=None):
        super().__init__(parent)
        v = QDoubleValidator(0.0, 1e12, 3, self)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        v.setLocale(QLocale.c())
        self.setValidator(v)
        self.setPlaceholderText(placeholder)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        # اتجاه LTR للأرقام مع محاذاة يمين لتتماشى مع باقي الحقول
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def value(self):
        try:
            return float(self.text())
        except ValueError:
            return 0.0

    def set_value(self, v, decimals=None):
        if v is None or v == "":
            self.setText("")
        elif decimals is not None:
            self.setText(f"{float(v):.{decimals}f}")
        else:
            f = float(v)
            self.setText(str(int(f)) if f == int(f) else f"{f:g}")


class ChoiceCard(QPushButton):
    def __init__(self, title, sub, value, parent=None):
        super().__init__(parent)
        self.setObjectName("choice")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.value = value
        lay = QHBoxLayout(self)
        lay.setContentsMargins(S4, S3, S4, S3)
        lay.setSpacing(S3)
        self.radio = QLabel()
        self.radio.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.radio)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = label(title, "choiceTitle")
        s = label(sub, "choiceSub")
        for w in (t, s):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            col.addWidget(w)
        lay.addLayout(col, 1)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggled.connect(self._sync)
        self._sync(False)

    def _sync(self, on):
        name, color = ("mdi6.radiobox-marked", C["accent"]) if on else ("mdi6.radiobox-blank", C["border_strong"])
        self.radio.setPixmap(qta.icon(name, color=color).pixmap(20, 20))
        for lb in self.findChildren(QLabel):
            repolish(lb)


class ChoiceGroup(QWidget):
    changed = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(S3)
        self.cards = []
        for title, sub, value in options:
            c = ChoiceCard(title, sub, value)
            c.clicked.connect(lambda _=False, v=value: self.changed.emit(v))
            lay.addWidget(c)
            self.cards.append(c)
        self.cards[0].setChecked(True)

    def value(self):
        for c in self.cards:
            if c.isChecked():
                return c.value
        return self.cards[0].value

    def set_value(self, v):
        for c in self.cards:
            if c.value == v:
                c.setChecked(True)
                return
        self.cards[0].setChecked(True)


_BANNER_ICONS = {
    "info": "mdi6.information-outline",
    "success": "mdi6.check-circle-outline",
    "warning": "mdi6.alert-outline",
    "danger": "mdi6.alert-circle-outline",
}


class Banner(QFrame):
    def __init__(self, text="", kind="info", parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(S3, S2 + 2, S3, S2 + 2)
        lay.setSpacing(S2 + 2)
        self.ic = QLabel()
        self.ic.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.text = label("", "bannerText", wrap=True)
        lay.addWidget(self.ic)
        lay.addWidget(self.text, 1)
        self._timer = QTimer(self, singleShot=True, timeout=self.hide)
        self.show_msg(text, kind, autohide=False)
        if not text:
            self.hide()

    def show_msg(self, text, kind="info", autohide=None):
        self.setProperty("kind", kind)
        kind = kind if kind in _BANNER_ICONS else "info"
        self.ic.setPixmap(qta.icon(_BANNER_ICONS[kind], color=C[kind]).pixmap(18, 18))
        self.text.setText(text)
        repolish(self)
        repolish(self.text)
        self.show()
        self._timer.stop()
        if autohide or (autohide is None and kind == "success"):
            self._timer.start(5000)


class StatTile(QFrame):
    def __init__(self, label_text, accent=False, parent=None):
        super().__init__(parent)
        self.setObjectName("stat")
        self.setProperty("accent", accent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4 + 2, S4, S4 + 2, S4)
        lay.setSpacing(S1)
        self.value = label("0", "statValue")
        self.label = label(label_text, "statLabel")
        lay.addWidget(self.label)
        lay.addWidget(self.value)

    def set_value(self, v):
        self.value.setText(str(v))


class Page(QWidget):
    """صفحة بعنوان كبير ووصف."""

    def __init__(self, title, subtitle, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(S8, S6 + 4, S8, S6)
        self.root.setSpacing(S4 + 4)
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(label(title, "pageTitle"))
        if subtitle:
            head.addWidget(label(subtitle, "pageSub", wrap=True))
        self.root.addLayout(head)
