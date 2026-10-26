"""الهوية البصرية: الثيمات، الألوان، الخطوط، المسافات، وورقة الأنماط (QSS).

الاتجاه الافتراضي: Windows 11 Fluent بأسطح متدرجة + جداول كثيفة للبيانات، مع لون
العلامة من النسخة الأصلية. كل الألوان تُشتق من بضع قيم أساسية لكل ثيم، لذلك أي ثيم
(فاتح أو داكن) وأي لون تمييز مخصّص يعطي واجهة متناسقة تلقائياً.
"""
import os
import re

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

from .data import data_dir, resource_path

# مقياس المسافات (أساس 4px)
S1, S2, S3, S4, S6, S8 = 4, 8, 12, 16, 24, 32

# الخطوط المرفقة مع التطبيق: (الاسم المعروض، اسم العائلة، بادئة الملفات)
BUNDLED_FONTS = [
    ("IBM Plex Sans Arabic (افتراضي)", "IBM Plex Sans Arabic", "IBMPlexSansArabic"),
    ("Cairo — القاهرة", "Cairo", "Cairo"),
    ("Tajawal — تجوّل", "Tajawal", "Tajawal"),
    ("Almarai — المراعي", "Almarai", "Almarai"),
    ("Noto Kufi Arabic — كوفي", "Noto Kufi Arabic", "NotoKufiArabic"),
    ("Noto Naskh Arabic — نسخ", "Noto Naskh Arabic", "NotoNaskhArabic"),
]
FALLBACK_FAMILIES = ["Segoe UI Variable", "Segoe UI", "Tahoma", "Arial"]

FONT_SCALES = [("صغير", "90%", 0.9), ("متوسط", "100%", 1.0), ("كبير", "112%", 1.12), ("كبير جداً", "125%", 1.25)]
RADII = [("حادة", "زوايا شبه مستقيمة", 0.35), ("متوسطة", "الافتراضي", 1.0), ("دائرية", "زوايا ناعمة", 1.7)]

# ---------- الثيمات ----------
_LIGHT = dict(dark=False, window="#F3F5F6", card="#FFFFFF", subtle="#F7F9FA", border="#E0E6E9",
              border_strong="#C9D3D7", text="#1B2428", text2="#56676E", text3="#7A8A90")
_DARK = dict(dark=True, window="#16191C", card="#1F2327", subtle="#1A1D21", border="#2E343A",
             border_strong="#3E464D", text="#E7EBEE", text2="#A8B2B9", text3="#87929A")

THEMES = {
    "teal": dict(_LIGHT, name="أزرق مخضر", sidebar="#0F3B4A", accent="#1A5F7A", accent2="#159895"),
    "ocean": dict(_LIGHT, name="أزرق محيطي", window="#F2F5F9", subtle="#F6F8FB", border="#DEE5EE",
                  border_strong="#C6D1DE", sidebar="#13284B", accent="#1F5FBF", accent2="#2D8CFF"),
    "forest": dict(_LIGHT, name="أخضر زيتي", window="#F2F5F1", subtle="#F6F8F5", border="#DFE6DC",
                   border_strong="#C7D2C3", text="#1C261E", text2="#55665A", text3="#78887C",
                   sidebar="#1C3A25", accent="#2E6B3F", accent2="#4C9A5E"),
    "violet": dict(_LIGHT, name="بنفسجي", window="#F4F3F8", subtle="#F8F7FB", border="#E3E0EE",
                   border_strong="#CDC8DD", text="#211D2C", text2="#5E5872", text3="#817B93",
                   sidebar="#2A1F4D", accent="#5B3FA6", accent2="#8A6BE0"),
    "sand": dict(_LIGHT, name="رملي دافئ", window="#F6F2EC", card="#FFFDF9", subtle="#FAF6F0",
                 border="#E8DFD2", border_strong="#D5C8B6", text="#2B2118", text2="#6B5B4B", text3="#8D7D6C",
                 sidebar="#3B2A1C", accent="#9A5B1E", accent2="#C98A3D"),
    "paper": dict(_LIGHT, name="فاتح بالكامل", window="#F5F6F7", sidebar="#FFFFFF", sidebar_text="#2E3A3F",
                  sidebar_muted="#6E7D83", accent="#1A5F7A", accent2="#159895"),
    "graphite": dict(_DARK, name="داكن", sidebar="#111316", accent="#2A93B0", accent2="#23B5A8"),
    "midnight": dict(_DARK, name="ليلي كحلي", window="#0F1522", card="#172033", subtle="#131B2B",
                     border="#26324A", border_strong="#33425F", text="#E6ECF5", text2="#A3B0C5", text3="#8090A8",
                     sidebar="#0B101B", accent="#3F7FE8", accent2="#6CA6FF"),
    "amber": dict(_DARK, name="داكن ذهبي", window="#171512", card="#211E1A", subtle="#1B1916",
                  border="#34302A", border_strong="#463F36", text="#EFE9E1", text2="#B9AEA0", text3="#968B7E",
                  sidebar="#110F0D", accent="#B07A1F", accent2="#D9A441"),
}

C = {}          # الألوان الفعّالة حالياً (تُملأ في apply)
STATE = {"family": "IBM Plex Sans Arabic", "font_scale": 1.0, "radius": 1.0}


def _mix(a, b, t):
    """يمزج اللون a باتجاه b بنسبة t (0..1)."""
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t), round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name().upper()


def _lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    q = QColor(c)
    return 0.2126 * ch(q.red()) + 0.7152 * ch(q.green()) + 0.0722 * ch(q.blue())


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def derive(base, accent=None):
    """يبني كل أدوار الألوان من القيم الأساسية للثيم."""
    b = dict(base)
    dark = b["dark"]
    if accent:
        b["accent"] = accent
        b["accent2"] = _mix(accent, "#FFFFFF", 0.25)
    acc, card = b["accent"], b["card"]
    side = b["sidebar"]
    side_light = _lum(side) > 0.5
    on_accent = "#FFFFFF" if _contrast("#FFFFFF", acc) >= 3 else "#111111"
    # لون نص التمييز فوق البطاقات يجب أن يكون مقروءاً
    accent_fg = acc
    while _contrast(accent_fg, card) < 4.5:
        accent_fg = _mix(accent_fg, "#FFFFFF" if dark else "#000000", 0.15)

    states = ({"success": "#4CC38A", "warning": "#E8B04A", "danger": "#F2766B", "info": "#5BC0DE"} if dark else
              {"success": "#17804F", "warning": "#8A5A00", "danger": "#C42B1C", "info": "#0B5A73"})
    soft_t, border_t = (0.16, 0.38) if dark else (0.10, 0.30)
    c = dict(b)
    c.update(
        on_accent=on_accent,
        accent_fg=accent_fg,
        accent_hover=_mix(acc, "#FFFFFF", 0.12) if dark else _mix(acc, "#000000", 0.15),
        accent_pressed=_mix(acc, "#000000", 0.25) if dark else _mix(acc, "#000000", 0.35),
        accent_soft=_mix(card, acc, 0.22 if dark else 0.10),
        accent_border=_mix(card, acc, 0.5),
        sidebar_text=b.get("sidebar_text") or ("#2E3A3F" if side_light else _mix(side, "#FFFFFF", 0.82)),
        sidebar_muted=b.get("sidebar_muted") or ("#6E7D83" if side_light else _mix(side, "#FFFFFF", 0.55)),
        sidebar_hover=_mix(side, "#000000" if side_light else "#FFFFFF", 0.06 if side_light else 0.08),
        sidebar_active=_mix(card, acc, 0.12) if side_light or dark else card,
        sidebar_active_text=accent_fg if (side_light or not dark) else "#FFFFFF",
        sidebar_border=b["border"] if side_light else side,
        input_bg=_mix(card, b["window"], 0.35) if dark else card,
        header_bg=_mix(card, b["text"], 0.07 if dark else 0.05),
        grid=_mix(card, b["text"], 0.06),
        scroll=b["border_strong"],
        scroll_hover=b["text3"],
        tooltip_bg="#000000" if dark else b["text"],
        disabled_bg=_mix(card, b["text"], 0.12),
        disabled_text=b["text3"],
        on_accent_muted=_mix(on_accent, acc, 0.25),
    )
    for k, v in states.items():
        c[k] = v
        c[k + "_soft"] = _mix(card, v, soft_t)
        c[k + "_border"] = _mix(card, v, border_t)
        c[k + "_hover"] = _mix(v, "#000000", 0.15) if not dark else _mix(v, "#FFFFFF", 0.12)
    c["on_success"] = "#FFFFFF" if _contrast("#FFFFFF", c["success"]) >= 3 else "#0D1F16"
    c["on_danger"] = "#FFFFFF" if _contrast("#FFFFFF", c["danger"]) >= 3 else "#2A0B08"
    c["auto_bg"], c["auto_border"] = c["success_soft"], c["success_border"]
    c["calc_bg"] = _mix(card, c["info"], 0.07 if not dark else 0.12)
    c["price_bg"] = c["warning_soft"]
    c["error_bg"] = _mix(card, c["danger"], 0.05 if not dark else 0.1)
    return c


# ---------- الخطوط ----------
def load_fonts():
    folder = resource_path("fonts")
    for fn in os.listdir(folder):
        if fn.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(folder, fn))


def system_arabic_fonts():
    bundled = {f for _, f, _ in BUNDLED_FONTS}
    fams = QFontDatabase.families(QFontDatabase.WritingSystem.Arabic)
    return sorted(f for f in fams if f not in bundled and not f.startswith("."))


def families():
    return [STATE["family"]] + [f for f in ["IBM Plex Sans Arabic"] + FALLBACK_FAMILIES if f != STATE["family"]]


def font(size=10, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(families())
    f.setPointSizeF(size * STATE["font_scale"])
    f.setWeight(weight)
    return f


# ---------- التطبيق ----------
def apply(app, settings):
    theme = THEMES.get(settings.get("theme")) or THEMES["teal"]
    C.clear()
    C.update(derive(theme, settings.get("accent")))
    STATE["family"] = settings.get("font") or "IBM Plex Sans Arabic"
    STATE["font_scale"] = float(settings.get("font_scale") or 1.0)
    STATE["radius"] = float(settings.get("radius") or 1.0)
    app.setFont(font())
    app.setPalette(palette())
    app.setStyleSheet(stylesheet())


def palette():
    p = QPalette()
    roles = QPalette.ColorRole
    for role, key in [(roles.Window, "window"), (roles.Base, "input_bg"), (roles.AlternateBase, "subtle"),
                      (roles.Text, "text"), (roles.WindowText, "text"), (roles.Button, "card"),
                      (roles.ButtonText, "text"), (roles.Highlight, "accent"), (roles.HighlightedText, "on_accent"),
                      (roles.PlaceholderText, "text3"), (roles.ToolTipBase, "tooltip_bg"),
                      (roles.ToolTipText, "card"), (roles.Light, "card"), (roles.Mid, "border"),
                      (roles.Dark, "border_strong")]:
        p.setColor(role, QColor(C[key]))
    p.setColor(roles.ToolTipText, QColor("#FFFFFF"))
    return p


def _chevron_path():
    """سهم القوائم المنسدلة بلون الثيم (يُكتب كملف لأن QSS يحتاج مساراً)."""
    folder = os.path.join(data_dir(), "ui")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"chevron-{C['text2'][1:]}.svg")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
                    f'<path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="{C["text2"]}" stroke-width="1.5" '
                    'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return path.replace("\\", "/")


def stylesheet():
    qss = _QSS % {**C, "arrow": _chevron_path(), "family": STATE["family"]}
    fs, rs = STATE["font_scale"], STATE["radius"]
    qss = re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * fs:.1f}pt", qss)
    # «border-radius: Npx» (بمسافة) يتغيّر مع خيار الزوايا؛ الأشكال الدائرية تُكتب بدون مسافة لتبقى ثابتة
    return re.sub(r"border-radius: (\d+)px", lambda m: f"border-radius: {max(0, round(int(m.group(1)) * rs))}px", qss)


_QSS = """
* { font-size: 10pt; color: %(text)s; }
QMainWindow, QDialog { background: %(window)s; }
QWidget#page, QWidget#scrollBody { background: %(window)s; }
QToolTip { background: %(tooltip_bg)s; color: #FFFFFF; border: none; padding: 4px 8px; border-radius: 4px; }
QLabel { background: transparent; }

/* ---------- الشريط الجانبي ---------- */
QFrame#sidebar { background: %(sidebar)s; border: none; border-left: 1px solid %(sidebar_border)s; }
QFrame#sidebarSep { background: %(sidebar_hover)s; border: none; }
QLabel#appTitle { color: %(sidebar_text)s; font-size: 13pt; font-weight: 700; }
QLabel#appSub { color: %(sidebar_muted)s; font-size: 8.5pt; }
QLabel#credit { color: %(sidebar_muted)s; font-size: 8pt; }
QLabel#logo { background: %(accent2)s; border-radius: 10px; }
QPushButton#nav {
    background: transparent; color: %(sidebar_text)s; border: none; border-radius: 8px;
    padding: 10px 12px; text-align: left; font-size: 10.5pt; font-weight: 500;
}
QPushButton#nav:hover { background: %(sidebar_hover)s; }
QPushButton#nav:checked { background: %(sidebar_active)s; color: %(sidebar_active_text)s; font-weight: 700; }
QPushButton#nav:focus { outline: none; }
QLabel#navBadge {
    background: %(accent2)s; color: #FFFFFF; border-radius:9px; padding: 0 7px;
    font-size: 8.5pt; font-weight: 700;
}

/* ---------- العناوين ---------- */
QLabel#pageTitle { font-size: 17pt; font-weight: 700; color: %(text)s; }
QLabel#pageSub { font-size: 9.5pt; color: %(text2)s; }
QLabel#sectionTitle { font-size: 12pt; font-weight: 700; color: %(accent_fg)s; }
QLabel#sectionSub, QLabel#caption { font-size: 8.5pt; color: %(text2)s; }
QLabel#fieldLabel { font-size: 9pt; font-weight: 600; color: %(text2)s; }
QLabel#subTitle { font-size: 10pt; font-weight: 700; color: %(accent_fg)s; }
QLabel#muted { color: %(text3)s; }
QLabel#stepNum {
    background: %(accent_soft)s; color: %(accent_fg)s; border-radius:12px;
    min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
    font-weight: 700; font-size: 9.5pt; qproperty-alignment: AlignCenter;
}
QLabel#autoTag {
    background: %(success_soft)s; color: %(success)s; border-radius: 4px;
    padding: 0 5px; font-size: 7.5pt; font-weight: 700;
}
QLabel#preview { font-size: 13pt; color: %(text)s; }

/* ---------- البطاقات ---------- */
QFrame#card { background: %(card)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#subCard { background: %(subtle)s; border: 1px solid %(border)s; border-radius: 8px; }
QFrame#divider { background: %(border)s; max-height: 1px; min-height: 1px; border: none; }
QFrame#actionBar { background: %(card)s; border: none; border-top: 1px solid %(border)s; }
QLabel#wallResult { background: %(success_soft)s; color: %(success)s; border-radius: 6px; padding: 6px 10px; }
QLabel#imageView { background: #FFFFFF; border: 1px solid %(border)s; border-radius: 8px; }

/* بطاقات الإحصاء */
QFrame#stat { background: %(card)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#stat[accent="true"] { background: %(accent)s; border: 1px solid %(accent)s; }
QLabel#statValue { font-size: 18pt; font-weight: 700; color: %(text)s; }
QLabel#statLabel { font-size: 9pt; color: %(text2)s; }
QFrame#stat[accent="true"] QLabel#statValue { color: %(on_accent)s; }
QFrame#stat[accent="true"] QLabel#statLabel { color: %(on_accent_muted)s; }

/* الكلفة الحية */
QFrame#liveCost { background: %(success_soft)s; border: 1px solid %(success_border)s; border-radius: 10px; }
QLabel#liveCostValue { font-size: 16pt; font-weight: 700; color: %(success)s; }
QLabel#liveCostLabel { font-size: 8.5pt; font-weight: 600; color: %(success)s; }
QLabel#liveCostNote { font-size: 8pt; color: %(warning)s; }

/* ---------- الأزرار ---------- */
QPushButton {
    background: %(accent)s; color: %(on_accent)s; border: 1px solid %(accent)s; border-radius: 6px;
    padding: 7px 16px; font-weight: 600;
}
QPushButton:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton:pressed { background: %(accent_pressed)s; border-color: %(accent_pressed)s; }
QPushButton:disabled { background: %(disabled_bg)s; border-color: %(disabled_bg)s; color: %(disabled_text)s; }
QPushButton:focus { outline: none; border: 1px solid %(accent_pressed)s; }

QPushButton#secondary { background: %(card)s; color: %(text)s; border: 1px solid %(border_strong)s; }
QPushButton#secondary:hover { background: %(subtle)s; border-color: %(accent)s; color: %(accent_fg)s; }
QPushButton#secondary:pressed { background: %(accent_soft)s; }
QPushButton#secondary:disabled { color: %(disabled_text)s; background: %(subtle)s; }
QPushButton#secondary[compact="true"], QPushButton#danger[compact="true"] { padding: 4px 10px; }

QPushButton#success { background: %(success)s; border-color: %(success)s; color: %(on_success)s; }
QPushButton#success:hover { background: %(success_hover)s; border-color: %(success_hover)s; }

QPushButton#danger { background: %(card)s; color: %(danger)s; border: 1px solid %(danger_border)s; }
QPushButton#danger:hover { background: %(danger_soft)s; border-color: %(danger)s; }
QPushButton#danger:pressed { background: %(danger_border)s; }
QPushButton#dangerSolid { background: %(danger)s; border-color: %(danger)s; color: %(on_danger)s; }
QPushButton#dangerSolid:hover { background: %(danger_hover)s; border-color: %(danger_hover)s; }

QPushButton#ghost { background: transparent; color: %(text2)s; border: 1px solid transparent; padding: 4px 8px; }
QPushButton#ghost:hover { background: %(subtle)s; color: %(accent_fg)s; border-color: %(border)s; }

QPushButton#iconRemove {
    background: %(card)s; color: %(danger)s; border: 1px solid %(border)s; border-radius:12px;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0;
}
QPushButton#iconRemove:hover { background: %(danger_soft)s; border-color: %(danger)s; }

/* بطاقات الاختيار */
QPushButton#choice {
    background: %(card)s; border: 1.5px solid %(border_strong)s; border-radius: 10px;
    padding: 10px 14px; min-height: 44px;
}
QPushButton#choice:hover { border-color: %(accent2)s; background: %(subtle)s; }
QPushButton#choice:checked { border: 1.5px solid %(accent)s; background: %(accent_soft)s; }
QLabel#choiceTitle { font-size: 10.5pt; font-weight: 700; color: %(text)s; }
QLabel#choiceSub { font-size: 8.5pt; color: %(text2)s; }
QPushButton#choice:checked QLabel#choiceTitle { color: %(accent_fg)s; }

/* بطاقات الثيمات */
QPushButton#themeCard {
    background: %(card)s; border: 1.5px solid %(border)s; border-radius: 10px; padding: 0;
}
QPushButton#themeCard:hover { border-color: %(accent2)s; }
QPushButton#themeCard:checked { border: 2px solid %(accent)s; }
QLabel#themeName { font-size: 9.5pt; font-weight: 600; color: %(text)s; }
QPushButton#swatch { border: 1px solid %(border_strong)s; border-radius:14px; padding: 0;
    min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; }
QPushButton#swatch:checked { border: 3px solid %(text)s; }

/* ---------- الحقول ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background: %(input_bg)s; border: 1px solid %(border_strong)s; border-radius: 6px;
    padding: 6px 10px; selection-background-color: %(accent)s; selection-color: %(on_accent)s;
    min-height: 20px; color: %(text)s;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover { border-color: %(text3)s; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid %(accent)s; }
QLineEdit:disabled, QComboBox:disabled { background: %(subtle)s; color: %(text3)s; }
QLineEdit[auto="true"] { background: %(auto_bg)s; border-color: %(auto_border)s; }
QLineEdit[auto="true"]:focus { border-color: %(success)s; }
QLineEdit:read-only { background: %(calc_bg)s; border-color: %(border)s; color: %(text)s; }
QLineEdit[error="true"] { border: 1px solid %(danger)s; background: %(error_bg)s; }

QComboBox { padding-left: 28px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center left; width: 24px; border: none; }
QComboBox::down-arrow { image: url(%(arrow)s); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: %(card)s; border: 1px solid %(border)s; border-radius: 6px; padding: 4px; color: %(text)s;
    selection-background-color: %(accent_soft)s; selection-color: %(accent_fg)s; outline: none;
}
QComboBox QAbstractItemView::item { min-height: 28px; padding: 0 8px; border-radius: 4px; }

/* ---------- الجداول ---------- */
QTableView, QTableWidget {
    background: %(card)s; border: 1px solid %(border)s; border-radius: 10px; color: %(text)s;
    alternate-background-color: %(subtle)s; gridline-color: %(grid)s;
    selection-background-color: %(accent_soft)s; selection-color: %(text)s; outline: none;
}
QTableView::item { padding: 4px 8px; border: none; }
QTableView::item:selected { background: %(accent_soft)s; color: %(text)s; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: %(header_bg)s; color: %(text2)s; font-weight: 700; font-size: 9pt;
    padding: 8px 10px; border: none; border-bottom: 1px solid %(border)s;
}
QTableCornerButton::section { background: %(header_bg)s; border: none; }

/* ---------- الشريط والتنبيهات ---------- */
QFrame#banner { border-radius: 8px; border: 1px solid transparent; }
QFrame#banner[kind="info"] { background: %(info_soft)s; border-color: %(info_border)s; }
QFrame#banner[kind="success"] { background: %(success_soft)s; border-color: %(success_border)s; }
QFrame#banner[kind="warning"] { background: %(warning_soft)s; border-color: %(warning_border)s; }
QFrame#banner[kind="danger"] { background: %(danger_soft)s; border-color: %(danger_border)s; }
QFrame#banner[kind="info"] QLabel#bannerText { color: %(info)s; }
QFrame#banner[kind="success"] QLabel#bannerText { color: %(success)s; }
QFrame#banner[kind="warning"] QLabel#bannerText { color: %(warning)s; }
QFrame#banner[kind="danger"] QLabel#bannerText { color: %(danger)s; }

/* بطاقات المرفقات وملف القطعة */
QFrame#attachCard { background: %(card)s; border: 1px solid %(border)s; border-radius: 8px; }
QFrame#attachCard:hover { border-color: %(accent2)s; }
QLabel#thumb { background: %(subtle)s; border-radius: 6px; }
QLabel#cadPreview { background: #FFFFFF; border: 1px solid %(border)s; border-radius: 8px; }
QFrame#dropZone { background: %(subtle)s; border: 1.5px dashed %(border_strong)s; border-radius: 10px; }

/* ---------- التمرير ---------- */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(scroll)s; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: %(scroll_hover)s; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(scroll)s; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: %(scroll_hover)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QMessageBox { background: %(window)s; }
QMessageBox QLabel { font-size: 10pt; }
QMenu { background: %(card)s; border: 1px solid %(border)s; padding: 4px; }
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 4px; }
QMenu::item:selected { background: %(accent_soft)s; color: %(accent_fg)s; }
"""
