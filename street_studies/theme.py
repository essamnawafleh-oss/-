"""الهوية البصرية: الألوان، الخطوط، المسافات، وورقة الأنماط (QSS).

الاتجاه: Windows 11 Fluent بأسطح متدرجة فاتحة + جداول كثيفة للبيانات،
مع لون العلامة (الأزرق المخضر) من النسخة الأصلية كلون التفاعل الوحيد.
"""
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

from .data import resource_path

# مقياس المسافات (أساس 4px)
S1, S2, S3, S4, S6, S8 = 4, 8, 12, 16, 24, 32

C = {
    "window": "#F3F5F6",
    "sidebar": "#0F3B4A",
    "sidebar_hover": "#18495A",
    "sidebar_active": "#FFFFFF",
    "sidebar_text": "#D5E4E9",
    "sidebar_muted": "#8FB0BB",
    "card": "#FFFFFF",
    "subtle": "#F7F9FA",
    "border": "#E0E6E9",
    "border_strong": "#C9D3D7",
    "text": "#1B2428",
    "text2": "#56676E",
    "text3": "#7A8A90",
    "accent": "#1A5F7A",
    "accent_hover": "#154E64",
    "accent_pressed": "#0F3B4A",
    "accent_soft": "#E6F1F4",
    "accent2": "#159895",
    "auto_bg": "#EAF6F1",
    "auto_border": "#B9DFCF",
    "calc_bg": "#EEF3F8",
    "success": "#17804F",
    "success_hover": "#126A41",
    "success_soft": "#E7F4EC",
    "warning": "#8A5A00",
    "warning_soft": "#FFF5DB",
    "danger": "#C42B1C",
    "danger_hover": "#A52416",
    "danger_soft": "#FCEBE9",
    "info": "#0B5A73",
    "info_soft": "#E4F3F8",
}

FONT_FAMILIES = ["IBM Plex Sans Arabic", "Segoe UI Variable", "Segoe UI", "Tahoma", "Arial"]
NUM_FAMILIES = ["Segoe UI Variable", "Segoe UI", "IBM Plex Sans Arabic", "Arial"]

# مقياس الخطوط (pt)
T_PAGE, T_SECTION, T_BODY, T_CAPTION, T_STAT = 17, 12.5, 10, 8.5, 18


def load_fonts():
    for w in ("400Regular", "500Medium", "600SemiBold", "700Bold"):
        QFontDatabase.addApplicationFont(resource_path("fonts", f"IBMPlexSansArabic_{w}.ttf"))


def font(size=T_BODY, weight=QFont.Weight.Normal, families=None):
    f = QFont()
    f.setFamilies(families or FONT_FAMILIES)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def palette():
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(C["window"]))
    p.setColor(QPalette.ColorRole.Base, QColor(C["card"]))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(C["subtle"]))
    p.setColor(QPalette.ColorRole.Text, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.Button, QColor(C["card"]))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.Highlight, QColor(C["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(C["text3"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    return p


def stylesheet():
    return """
* { font-size: 10pt; color: %(text)s; }
QMainWindow, QDialog { background: %(window)s; }
QWidget#page, QWidget#scrollBody { background: %(window)s; }
QToolTip { background: %(text)s; color: #FFFFFF; border: none; padding: 4px 8px; border-radius: 4px; }

/* ---------- الشريط الجانبي ---------- */
QFrame#sidebar { background: %(sidebar)s; border: none; }
QLabel#appTitle { color: #FFFFFF; font-size: 13pt; font-weight: 700; }
QLabel#appSub { color: %(sidebar_muted)s; font-size: 8.5pt; }
QLabel#credit { color: %(sidebar_muted)s; font-size: 8pt; }
QPushButton#nav {
    background: transparent; color: %(sidebar_text)s; border: none; border-radius: 8px;
    padding: 10px 12px; text-align: left; font-size: 10.5pt; font-weight: 500;
}
QPushButton#nav:hover { background: %(sidebar_hover)s; color: #FFFFFF; }
QPushButton#nav:checked { background: %(sidebar_active)s; color: %(accent)s; font-weight: 700; }
QPushButton#nav:focus { outline: none; }
QLabel#navBadge {
    background: %(accent2)s; color: #FFFFFF; border-radius: 9px; padding: 0 7px;
    font-size: 8.5pt; font-weight: 700; min-height: 18px;
}

/* ---------- العناوين ---------- */
QLabel#pageTitle { font-size: 17pt; font-weight: 700; color: %(text)s; }
QLabel#pageSub { font-size: 9.5pt; color: %(text2)s; }
QLabel#sectionTitle { font-size: 12pt; font-weight: 700; color: %(accent_pressed)s; }
QLabel#sectionSub, QLabel#caption { font-size: 8.5pt; color: %(text2)s; }
QLabel#fieldLabel { font-size: 9pt; font-weight: 600; color: %(text2)s; }
QLabel#muted { color: %(text3)s; }
QLabel#stepNum {
    background: %(accent_soft)s; color: %(accent)s; border-radius: 12px;
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
    font-weight: 700; font-size: 9.5pt; qproperty-alignment: AlignCenter;
}
QLabel#autoTag {
    background: %(success_soft)s; color: %(success)s; border-radius: 4px;
    padding: 0 5px; font-size: 7.5pt; font-weight: 700;
}

/* ---------- البطاقات ---------- */
QFrame#card { background: %(card)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#subCard { background: %(subtle)s; border: 1px solid %(border)s; border-radius: 8px; }
QFrame#divider { background: %(border)s; max-height: 1px; min-height: 1px; border: none; }
QFrame#actionBar { background: %(card)s; border: none; border-top: 1px solid %(border)s; }

/* بطاقات الإحصاء */
QFrame#stat { background: %(card)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#stat[accent="true"] { background: %(accent)s; border: 1px solid %(accent)s; }
QLabel#statValue { font-size: 18pt; font-weight: 700; color: %(text)s; }
QLabel#statLabel { font-size: 9pt; color: %(text2)s; }
QFrame#stat[accent="true"] QLabel#statValue { color: #FFFFFF; }
QFrame#stat[accent="true"] QLabel#statLabel { color: #CFE3EA; }

/* الكلفة الحية */
QFrame#liveCost { background: %(success_soft)s; border: 1px solid #BFE0CC; border-radius: 10px; }
QLabel#liveCostValue { font-size: 16pt; font-weight: 700; color: %(success)s; }
QLabel#liveCostLabel { font-size: 8.5pt; font-weight: 600; color: %(success)s; }
QLabel#liveCostNote { font-size: 8pt; color: %(warning)s; }

/* ---------- الأزرار ---------- */
QPushButton {
    background: %(accent)s; color: #FFFFFF; border: 1px solid %(accent)s; border-radius: 6px;
    padding: 7px 16px; font-weight: 600;
}
QPushButton:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton:pressed { background: %(accent_pressed)s; border-color: %(accent_pressed)s; }
QPushButton:disabled { background: #D5DCDF; border-color: #D5DCDF; color: #8A979C; }
QPushButton:focus { outline: none; border: 1px solid %(accent_pressed)s; }

QPushButton#secondary { background: %(card)s; color: %(text)s; border: 1px solid %(border_strong)s; }
QPushButton#secondary:hover { background: %(subtle)s; border-color: %(accent)s; color: %(accent)s; }
QPushButton#secondary:pressed { background: %(accent_soft)s; }
QPushButton#secondary:disabled { color: #9AA6AB; background: %(subtle)s; }

QPushButton#success { background: %(success)s; border-color: %(success)s; }
QPushButton#success:hover { background: %(success_hover)s; border-color: %(success_hover)s; }

QPushButton#danger { background: %(card)s; color: %(danger)s; border: 1px solid #EBC3BE; }
QPushButton#danger:hover { background: %(danger_soft)s; border-color: %(danger)s; }
QPushButton#danger:pressed { background: #F7D6D2; }
QPushButton#dangerSolid { background: %(danger)s; border-color: %(danger)s; }
QPushButton#dangerSolid:hover { background: %(danger_hover)s; border-color: %(danger_hover)s; }

QPushButton#ghost { background: transparent; color: %(text2)s; border: 1px solid transparent; padding: 4px 8px; }
QPushButton#ghost:hover { background: %(subtle)s; color: %(accent)s; border-color: %(border)s; }

QPushButton#iconRemove {
    background: %(card)s; color: %(danger)s; border: 1px solid %(border)s; border-radius: 12px;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0;
}
QPushButton#iconRemove:hover { background: %(danger_soft)s; border-color: %(danger)s; }

/* بطاقات الاختيار */
QPushButton#choice {
    background: %(card)s; border: 1.5px solid %(border_strong)s; border-radius: 10px;
    padding: 10px 14px; min-height: 44px;
}
QPushButton#choice:hover { border-color: %(accent2)s; background: #F2FAF9; }
QPushButton#choice:checked { border: 1.5px solid %(accent)s; background: %(accent_soft)s; }
QLabel#choiceTitle { font-size: 10.5pt; font-weight: 700; color: %(text)s; background: transparent; }
QLabel#choiceSub { font-size: 8.5pt; color: %(text2)s; background: transparent; }
QPushButton#choice:checked QLabel#choiceTitle { color: %(accent)s; }

/* ---------- الحقول ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background: %(card)s; border: 1px solid %(border_strong)s; border-radius: 6px;
    padding: 6px 10px; selection-background-color: %(accent)s; selection-color: #FFFFFF;
    min-height: 20px;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover { border-color: #AEBBC0; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1px solid %(accent)s; background: #FFFFFF;
}
QLineEdit:disabled, QComboBox:disabled { background: %(subtle)s; color: %(text3)s; }
QLineEdit[auto="true"] { background: %(auto_bg)s; border-color: %(auto_border)s; }
QLineEdit[auto="true"]:focus { border-color: %(success)s; }
QLineEdit:read-only { background: %(calc_bg)s; border-color: %(border)s; color: %(text)s; }
QLineEdit[error="true"] { border: 1px solid %(danger)s; background: #FFF8F7; }

QComboBox { padding-left: 28px; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center left; width: 24px; border: none;
}
QComboBox::down-arrow { image: url(%(arrow)s); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: %(card)s; border: 1px solid %(border)s; border-radius: 6px; padding: 4px;
    selection-background-color: %(accent_soft)s; selection-color: %(accent)s; outline: none;
}
QComboBox QAbstractItemView::item { min-height: 28px; padding: 0 8px; border-radius: 4px; }

/* ---------- الجداول ---------- */
QTableView, QTableWidget {
    background: %(card)s; border: 1px solid %(border)s; border-radius: 10px;
    alternate-background-color: %(subtle)s; gridline-color: #EDF1F2;
    selection-background-color: %(accent_soft)s; selection-color: %(text)s; outline: none;
}
QTableView::item { padding: 4px 8px; border: none; }
QTableView::item:selected { background: %(accent_soft)s; color: %(text)s; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: #EEF2F4; color: %(text2)s; font-weight: 700; font-size: 9pt;
    padding: 8px 10px; border: none; border-bottom: 1px solid %(border)s;
}
QTableCornerButton::section { background: #EEF2F4; border: none; }

/* ---------- الشريط والتنبيهات ---------- */
QFrame#banner { border-radius: 8px; border: 1px solid transparent; }
QFrame#banner[kind="info"] { background: %(info_soft)s; border-color: #BFE1EC; }
QFrame#banner[kind="success"] { background: %(success_soft)s; border-color: #BFE0CC; }
QFrame#banner[kind="warning"] { background: %(warning_soft)s; border-color: #F1DDA6; }
QFrame#banner[kind="danger"] { background: %(danger_soft)s; border-color: #F0C4BF; }
QLabel#bannerText { background: transparent; }
QFrame#banner[kind="info"] QLabel#bannerText { color: %(info)s; }
QFrame#banner[kind="success"] QLabel#bannerText { color: %(success)s; }
QFrame#banner[kind="warning"] QLabel#bannerText { color: %(warning)s; }
QFrame#banner[kind="danger"] QLabel#bannerText { color: %(danger)s; }

/* بطاقات المرفقات */
QFrame#attachCard { background: %(card)s; border: 1px solid %(border)s; border-radius: 8px; }
QFrame#attachCard:hover { border-color: %(accent2)s; }
QLabel#thumb { background: %(subtle)s; border-radius: 6px; }

/* ---------- التمرير ---------- */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #C3CDD1; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #9DABB1; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #C3CDD1; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: #9DABB1; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QMessageBox QLabel { font-size: 10pt; }
""" % {**C, "arrow": resource_path("chevron-down.svg").replace("\\", "/")}
