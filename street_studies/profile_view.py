"""نافذة البروفايل الطولي: رسم الأرض والمنسوب التصميمي والمقاطع المخالفة، مع ملخص وإعدادات."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget,
)

from . import profile
from .theme import C, S2, S3, S4
from .widgets import Banner, Field, NumberEdit, button, grid, label

COL = {"ground": "#8D6E63", "design": "#1565C0", "edge": "#BCAAA4", "bad": "#D32F2F", "band": QColor(46, 125, 50, 38)}


class ProfilePlot(QWidget):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setMinimumSize(760, 360)

    def paintEvent(self, _e):
        p = QPainter(self)
        draw_profile(p, self.rect(), self.data, background=C.get("card", "#FFFFFF"),
                     text=C.get("text", "#1B2428"), grid_col=C.get("border", "#E0E6E9"))
        p.end()


def draw_profile(p, rect, d, background="#FFFFFF", text="#1B2428", grid_col="#E0E6E9"):
    """يرسم بروفايلاً واحداً داخل rect (يُستخدم في النافذة وفي صورة التقرير)."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(rect, QColor(background))
    st = d["stations"]
    if len(st) < 2:
        return
    gmax, cf = d["params"]["max_grade"], d["params"]["max_cutfill"]
    zs = [v for s in st for v in (s["zc"], s["zl"], s["zr"], s["zd"])]
    z0, z1 = min(zs) - 2, max(zs) + 2
    s0, s1 = st[0]["s"], st[-1]["s"]
    L, R, T, B = rect.left() + 64, rect.right() - 16, rect.top() + 16, rect.bottom() - 40

    def X(s):
        return L + (s - s0) / max(s1 - s0, 1e-6) * (R - L)

    def Y(z):
        return B - (z - z0) / max(z1 - z0, 1e-6) * (B - T)

    f = QFont()
    f.setPixelSize(11)
    p.setFont(f)
    # الشبكة والمحاور
    p.setPen(QPen(QColor(grid_col), 1))
    zstep = _nice((z1 - z0) / 6)
    z = (int(z0 / zstep) + 1) * zstep
    while z < z1:
        p.drawLine(QPointF(L, Y(z)), QPointF(R, Y(z)))
        p.setPen(QColor(text))
        p.drawText(QRectF(rect.left() + 2, Y(z) - 8, 58, 16), Qt.AlignmentFlag.AlignRight, f"{z:g}")
        p.setPen(QPen(QColor(grid_col), 1))
        z += zstep
    sstep = _nice((s1 - s0) / 8)
    s = (int(s0 / sstep)) * sstep
    while s <= s1 + 1e-6:
        if s >= s0:
            p.drawLine(QPointF(X(s), T), QPointF(X(s), B))
            p.setPen(QColor(text))
            p.drawText(QRectF(X(s) - 30, B + 4, 60, 16), Qt.AlignmentFlag.AlignCenter, f"{s:g}")
            p.setPen(QPen(QColor(grid_col), 1))
        s += sstep
    p.setPen(QColor(text))
    p.drawText(QRectF(L, B + 20, R - L, 16), Qt.AlignmentFlag.AlignCenter, "المسافة على طول الشارع (م)")

    # النطاق المسموح للمنسوب التصميمي (±حد القطع/الردم عن الواجهتين)
    top = [QPointF(X(q["s"]), Y(min(q["zl"], q["zr"]) + cf)) for q in st]
    bot = [QPointF(X(q["s"]), Y(max(q["zl"], q["zr"]) - cf)) for q in reversed(st)]
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(COL["band"])
    p.drawPolygon(QPolygonF(top + bot))

    def line(key, color, width=2.0, dash=False):
        path = QPainterPath(QPointF(X(st[0]["s"]), Y(st[0][key])))
        for q in st[1:]:
            path.lineTo(QPointF(X(q["s"]), Y(q[key])))
        pen = QPen(QColor(color), width)
        if dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    line("zl", COL["edge"], 1.2, True)
    line("zr", COL["edge"], 1.2, True)
    line("zc", COL["ground"], 2.4)
    line("zd", COL["design"], 2.4)
    # المقاطع التي يتجاوز ميلها الحد
    for a, b in zip(st, st[1:]):
        ds = b["s"] - a["s"]
        if ds <= 0:
            continue
        if abs(b["zc"] - a["zc"]) / ds > gmax + 0.005:
            p.setPen(QPen(QColor(COL["bad"]), 4.5))
            p.drawLine(QPointF(X(a["s"]), Y(a["zc"])), QPointF(X(b["s"]), Y(b["zc"])))
        if abs(b["zd"] - a["zd"]) / ds > gmax + 0.005:
            p.setPen(QPen(QColor(COL["bad"]), 4.5, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(X(a["s"]), Y(a["zd"])), QPointF(X(b["s"]), Y(b["zd"])))
    # نقاط تجاوز القطع/الردم على الواجهة
    p.setPen(QPen(QColor("#FFFFFF"), 1))
    p.setBrush(QColor(COL["bad"]))
    for q in st:
        if q.get("bad_cf"):
            p.drawEllipse(QPointF(X(q["s"]), Y(q["zd"])), 4, 4)

    # مفتاح الرسم
    items = [(COL["ground"], "سطح الأرض (المحور)"), (COL["design"], "المنسوب التصميمي"),
             (COL["edge"], "الأرض عند الواجهتين"), (COL["bad"], f"ميل > {gmax * 100:g}% / قطع أو ردم > {cf:g} م")]
    x = R - 10
    for col, t in items:
        w = p.fontMetrics().horizontalAdvance(t) + 26
        x -= w
        p.setPen(QPen(QColor(col), 3))
        p.drawLine(QPointF(x, T + 8), QPointF(x + 16, T + 8))
        p.setPen(QColor(text))
        p.drawText(QPointF(x + 20, T + 12), t)


def _nice(v):
    import math
    if v <= 0:
        return 1
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


def render_image(d, w=1600, h=620):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    draw_profile(p, QRectF(0, 0, w, h), d)
    p.end()
    return img


def summary_lines(d):
    g = d["params"]["max_grade"] * 100
    cf = d["params"]["max_cutfill"]
    out = [f"طول المسار: {d['length']:.1f} م · الميل العام للأرض: {d.get('overall_grade', 0) * 100:.1f}%",
           f"أقصى ميل للأرض: {d['max_ground_grade'] * 100:.1f}% — مقاطع تتجاوز {g:g}%: {d['ground_over']}",
           f"أقصى ميل تصميمي: {d['max_design_grade'] * 100:.1f}% — مقاطع مخالفة: {d['design_over']}",
           f"أقصى قطع على الواجهة: {d['max_cut']:.2f} م · أقصى ردم: {d['max_fill']:.2f} م — نقاط تتجاوز {cf:g} م: {d['cf_over']}",
           f"الحفر: {d['cut']:.1f} م³ · الردم: {d['fill']:.1f} م³"]
    return out


class ProfileDialog(QDialog):
    """apply_requested(result) عند الضغط على «تطبيق الكميات»."""
    apply_requested = Signal(dict)

    def __init__(self, roads, width, terrain, params=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("البروفايل الطولي للشارع")
        self.roads, self.width_m, self.terrain = roads, width, terrain
        params = params or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(S4, S4, S4, S4)
        lay.setSpacing(S3)
        lay.addWidget(label("البروفايل الطولي — ميل الشارع والمنسوب التصميمي", "sectionTitle"))
        self.g = NumberEdit()
        self.g.set_value(params.get("max_grade", 0.19) * 100)
        self.cf = NumberEdit()
        self.cf.set_value(params.get("max_cutfill", 4.0))
        self.step = NumberEdit()
        self.step.set_value(params.get("step", 5.0))
        again = button("إعادة الحساب", "secondary", "mdi6.refresh")
        again.clicked.connect(self.recompute)
        row = QHBoxLayout()
        row.setSpacing(S3)
        row.addLayout(grid([Field("أقصى ميل (%)", self.g), Field("أقصى قطع/ردم على الواجهة (م)", self.cf),
                            Field("طول المقطع للفحص (م)", self.step)], 3), 1)
        row.addWidget(again, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(row)
        info = f"الكنتور: {terrain.zmin:g}–{terrain.zmax:g} م"
        if terrain.interval:
            info += f" · الفاصل {terrain.interval:g} م"
        lay.addWidget(label(info + " · عرض الشارع " + f"{width:g} م", "caption"))
        self.banner = Banner()
        lay.addWidget(self.banner)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = button("إغلاق", "secondary")
        close.clicked.connect(self.reject)
        self.apply_btn = button("تطبيق الحفر والردم على النموذج", "success", "mdi6.check")
        self.apply_btn.clicked.connect(self._apply)
        btns.addWidget(close)
        btns.addWidget(self.apply_btn)
        lay.addLayout(btns)
        self.resize(1080, 760)
        self.result = None
        self.recompute()

    def params(self):
        return {"max_grade": (self.g.value() or 19) / 100, "max_cutfill": self.cf.value() or 4.0,
                "step": max(self.step.value() or 5.0, 1.0)}

    def recompute(self):
        self.tabs.clear()
        try:
            self.result = profile.compute_all(self.roads, self.width_m, self.terrain, **self.params())
        except ValueError as e:
            self.result = None
            self.banner.show_msg(str(e), "danger", autohide=False)
            self.apply_btn.setEnabled(False)
            return
        self.apply_btn.setEnabled(True)
        msgs = []
        for n, d in enumerate(self.result["roads"], 1):
            page = QWidget()
            v = QVBoxLayout(page)
            v.setContentsMargins(S2, S2, S2, S2)
            v.addWidget(ProfilePlot(d), 1)
            t = QLabel("<br>".join(summary_lines(d)))
            t.setObjectName("caption")
            t.setWordWrap(True)
            v.addWidget(t)
            self.tabs.addTab(page, f"خط الشارع {n}")
            if d.get("alignment_impossible"):
                msgs.append(f"الخط {n}: فرق المنسوب يحتاج طولاً لا يقل عن {d['min_length_needed']:g} م بميل "
                            f"{d['params']['max_grade'] * 100:g}% (الطول الحالي {d['length']:.0f} م) — "
                            "يلزم تغيير مسار الشارع (التفاف) لتحقيق الحد.")
            elif d["design_over"] or d["cf_over"]:
                msgs.append(f"الخط {n}: تعذّر تحقيق الشرطين في {d['design_over']} مقطع ميل و{d['cf_over']} نقطة "
                            "قطع/ردم — الأحمر في الرسم.")
        if msgs:
            self.banner.show_msg("\n".join(msgs), "warning", autohide=False)
        else:
            self.banner.show_msg(f"المنسوب التصميمي يحقق الشرطين على كامل المسار ✓ — الحفر {self.result['cut']:.1f} م³، "
                                 f"الردم {self.result['fill']:.1f} م³", "success", autohide=False)

    def _apply(self):
        if self.result:
            self.apply_requested.emit(self.result)
            self.accept()
