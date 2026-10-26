"""النافذة الرئيسية: شريط جانبي للتنقل + صفحات."""
import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .data import Store, resource_path
from .pages.entry import EntryPage
from .pages.export import ExportPage
from .pages.prices import PricesPage
from .pages.streets_list import StreetsListPage
from .pages.summary import SummaryPage
from .theme import C, S1, S2, S4, S6
from .widgets import label

NAV = [
    ("entry", "إدخال الشوارع", "mdi6.road-variant"),
    ("list", "قائمة الشوارع", "mdi6.format-list-bulleted"),
    ("prices", "الأسعار والبنود", "mdi6.tag-outline"),
    ("summary", "الملخص", "mdi6.chart-box-outline"),
    ("export", "تصدير Excel", "mdi6.microsoft-excel"),
]


class NavButton(QPushButton):
    def __init__(self, text, icon_name):
        super().__init__(text)
        self.setObjectName("nav")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(qta.icon(icon_name, color=C["sidebar_text"], color_active=C["sidebar_text"],
                              color_on=C["accent"], color_on_active=C["accent"]))
        self.setIconSize(self.iconSize() * 1.25)
        self.badge = None

    def add_badge(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(S2, 0, S2, 0)
        lay.addStretch(1)
        self.badge = label("0", "navBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedHeight(20)
        self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)


class MainWindow(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.setWindowTitle("تطبيق دراسات الشوارع الذكي")
        self.setWindowIcon(QIcon(resource_path("app.ico")))
        self.resize(1280, 820)
        self.setMinimumSize(1040, 640)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.setCentralWidget(root)

        h.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)

        self.pages = {
            "entry": EntryPage(self.store),
            "list": StreetsListPage(self.store),
            "prices": PricesPage(self.store),
            "summary": SummaryPage(self.store),
            "export": ExportPage(self.store),
        }
        for key, _, _ in NAV:
            self.stack.addWidget(self.pages[key])

        self.pages["entry"].saved.connect(self.update_badge)
        self.pages["list"].edit_requested.connect(self.edit_street)
        self.pages["list"].changed.connect(self.update_badge)
        self.pages["prices"].changed.connect(self.pages["entry"].update_live_cost)
        self.pages["export"].data_restored.connect(self.on_restored)

        self.go("entry")
        self.update_badge()

    def _sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(248)
        v = QVBoxLayout(side)
        v.setContentsMargins(S4, S6, S4, S4)
        v.setSpacing(S1)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(qta.icon("mdi6.road-variant", color="#FFFFFF").pixmap(28, 28))
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(f"background:{C['accent2']}; border-radius:10px;")
        brand.addWidget(logo)
        t = QVBoxLayout()
        t.setSpacing(0)
        t.addWidget(label("دراسات الشوارع", "appTitle"))
        t.addWidget(label("التطبيق الذكي لحساب الكلف", "appSub"))
        brand.addLayout(t, 1)
        v.addLayout(brand)
        v.addSpacing(S6)

        self.nav = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, text, ic in NAV:
            b = NavButton(text, ic)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            group.addButton(b)
            v.addWidget(b)
            self.nav[key] = b
        self.nav["list"].add_badge()

        v.addStretch(1)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C['sidebar_hover']};")
        v.addWidget(sep)
        v.addSpacing(S2)
        v.addWidget(label("مناطق · طبيعة عطاء · نوع خلطة · جدران متعددة · تصدير Excel", "credit", wrap=True))
        v.addSpacing(S1)
        v.addWidget(label("تم عمل هذا التطبيق بواسطة\nالمهندس عمر الحمادين", "credit", wrap=True))
        return side

    def go(self, key):
        self.nav[key].setChecked(True)
        page = self.pages[key]
        if hasattr(page, "refresh"):
            page.refresh()
        self.stack.setCurrentWidget(page)

    def edit_street(self, idx):
        self.pages["entry"].edit_street(idx)
        self.nav["entry"].setChecked(True)
        self.stack.setCurrentWidget(self.pages["entry"])

    def update_badge(self):
        self.nav["list"].badge.setText(str(len(self.store.streets)))

    def on_restored(self):
        self.pages["entry"].clear_form()
        self.update_badge()
