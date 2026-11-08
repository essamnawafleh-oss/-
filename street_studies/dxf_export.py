"""ملف DXF لمسار مواطن: القطعة المحددة، والمحيط من المخطط التنظيمي، والشارع والجدران والبنود — بإحداثيات JTM.

أسماء الطبقات مأخوذة من أسماء البنود، ويُكتب اسم الطبقة (مع الكمية) بجوار كل رسم.
طبقات التصريف لكل منها لون ونوع خط وسماكة مختلفة حتى لا تتشابه.
"""
import math
import re

import ezdxf
from ezdxf.enums import MTextEntityAlignment, TextEntityAlignment
from PySide6.QtCore import QRectF

# طبقات ثابتة: الاسم ← (اللون، نوع الخط، السماكة 1/100 مم)
FIXED = {
    "القطعة المحددة": (4, "Continuous", 50),
    "قطع المخطط التنظيمي": (2, "Continuous", 13),
    "شوارع تنظيمية": (1, "Continuous", 25),
    "أودية ومجاري مياه": (5, "DASHED", 35),
    "شارع": (30, "Continuous", 30),
    "ملاحظات": (7, "Continuous", 18),
}
# خصائص مميزة لكل بند تصريف (لون، نوع خط، سماكة)
# الألوان مختارة بحيث لا تتكرر مع بعضها ولا مع طبقات المخطط التنظيمي (أحمر 1، أزرق 5، أصفر 2)
DRAIN_STYLES = {
    "DRN-001": (150, "DASHED", 35),     # أنبوب Ø400  — أزرق سماوي، متقطع
    "DRN-002": (94, "DASHDOT", 50),     # أنبوب Ø600  — أخضر، شرطة ونقطة
    "DRN-003": (40, "CENTER", 70),      # أنبوب Ø1000 — برتقالي، خط محوري
    "DRN-004": (200, "PHANTOM", 90),    # أنبوب Ø1200 — بنفسجي، فانتوم
    "DRN-005": (130, "Continuous", 50), # منهل تصريف  — فيروزي
    "DRN-006": (242, "DIVIDE", 40),     # جرلات       — وردي، مقسّم
}
_EXTRA_DRAIN = [(170, "DOT", 35), (62, "DASHEDX2", 50), (12, "DASHDOT2", 35), (182, "CENTER2", 60),
                (222, "DIVIDE2", 50), (82, "PHANTOM2", 35)]
# ألوان مميزة لباقي البنود حسب ترتيبها
_PALETTE = [3, 6, 30, 140, 210, 90, 230, 20, 110, 180, 250, 62, 120, 32, 160, 52, 190, 102]
WALL_STYLES = {"RD-005": (32, "Continuous", 60), "RD-006": (8, "Continuous", 70)}


def layer_name(name):
    """اسم طبقة صالح في أوتوكاد (يحذف الرموز الممنوعة)."""
    n = re.sub(r'[<>/\\":;?*|=`,]', " ", str(name or "")).strip()
    return re.sub(r"\s+", " ", n)[:120] or "بند"


def _midpoint(P):
    total = sum(math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]) for i in range(1, len(P)))
    half = 0.0
    for j in range(1, len(P)):
        seg = math.hypot(P[j][0] - P[j - 1][0], P[j][1] - P[j - 1][1])
        if seg and half + seg >= total / 2:
            t = (total / 2 - half) / seg
            ang = math.degrees(math.atan2(P[j][1] - P[j - 1][1], P[j][0] - P[j - 1][0]))
            return (P[j - 1][0] + (P[j][0] - P[j - 1][0]) * t, P[j - 1][1] + (P[j][1] - P[j - 1][1]) * t), ang
        half += seg
    return tuple(P[0]), 0.0


def _length(P):
    return sum(math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]) for i in range(1, len(P)))


def _area(P):
    return abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))) / 2


class _Writer:
    def __init__(self, store_items):
        self.doc = ezdxf.new("R2010", setup=True)
        self.doc.header["$LTSCALE"] = 2.0
        self.doc.header["$INSUNITS"] = 6  # متر
        self.doc.styles.add("ARABIC", font="arial.ttf")
        self.msp = self.doc.modelspace()
        self.items = {it["code"]: it for it in store_items}
        self.extra_drain = 0
        for name, style in FIXED.items():
            self._layer(name, style)

    def _layer(self, name, style):
        name = layer_name(name)
        if name not in self.doc.layers:
            color, ltype, lw = style
            if ltype not in self.doc.linetypes:
                ltype = "Continuous"
            self.doc.layers.add(name, color=color, linetype=ltype, lineweight=lw)
        return name

    def item_layer(self, code):
        it = self.items.get(code) or {"name": code, "group": ""}
        if code in DRAIN_STYLES:
            style = DRAIN_STYLES[code]
        elif code in WALL_STYLES:
            style = WALL_STYLES[code]
        elif "تصريف" in (it.get("group") or ""):
            style = _EXTRA_DRAIN[self.extra_drain % len(_EXTRA_DRAIN)]
            self.extra_drain += 1
        else:
            idx = list(self.items).index(code) if code in self.items else len(self.doc.layers)
            style = (_PALETTE[idx % len(_PALETTE)], "Continuous", 35)
        return self._layer(it["name"], style)

    def label(self, layer, P, text, height=1.2):
        """اسم الطبقة (والكمية) بجوار الرسم، موازٍ للخط ومُزاح قليلاً عنه."""
        if not P:
            return
        if len(P) == 1:
            pos, ang = tuple(P[0]), 0.0
        else:
            pos, ang = _midpoint(P)
        if ang > 90 or ang < -90:   # حتى لا يُقرأ النص مقلوباً
            ang += 180
        off = height * 0.9
        x = pos[0] - off * math.sin(math.radians(ang))
        y = pos[1] + off * math.cos(math.radians(ang))
        m = self.msp.add_mtext(text, dxfattribs={"layer": layer, "style": "ARABIC", "char_height": height,
                                                 "rotation": ang})
        m.set_location((x, y), attachment_point=MTextEntityAlignment.BOTTOM_CENTER)

    def poly(self, layer, P, close=False, width=None):
        attrs = {"layer": layer}
        if width:
            attrs["const_width"] = width
        self.msp.add_lwpolyline(P, close=close, dxfattribs=attrs)


def _clip(ds, i, box, closed):
    """العناصر الكبيرة (شارع طويل، مضلع واسع) تُقص على منطقة المحيط حتى لا يتضخم الملف ومداه."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF
    r, poly = ds.bbox[i], ds.polys[i]
    pad = box.adjusted(-box.width() * .25, -box.height() * .25, box.width() * .25, box.height() * .25)
    if pad.contains(r):
        return [([(poly.at(k).x(), poly.at(k).y()) for k in range(poly.size())], closed)]
    if closed:
        rect = QPolygonF([box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft()])
        cut = poly.intersected(rect)
        return [([(cut.at(k).x(), cut.at(k).y()) for k in range(cut.size())], True)] if cut.size() > 2 else []
    parts, run = [], []
    big = box.adjusted(-box.width() * .2, -box.height() * .2, box.width() * .2, box.height() * .2)
    for k in range(poly.size()):
        q = poly.at(k)
        if big.contains(QPointF(q)):
            run.append((q.x(), q.y()))
        elif run:
            parts.append(run)
            run = []
    if len(run) > 1:
        parts.append(run)
    return [(p, False) for p in parts if len(p) > 1]


def write_path_dxf(path, name, out_file, store_items=None):
    from .data import DEFAULT_ITEMS
    wr = _Writer(store_items or DEFAULT_ITEMS)
    msp = wr.msp

    # المحيط من المخطط التنظيمي ضمن الهامش حول القطعة والرسم
    pts = [q for k in ("roads", "wallsR", "wallsC") for P in path.get(k) or [] for q in P] + \
          (path.get("parcelPts") or [])
    if pts:
        try:
            from . import geo
            g = geo.GeoStore.get()
            m = float(path.get("margin") or 0)
            xs, ys = [p[0] - g.ox for p in pts], [p[1] - g.oy for p in pts]
            box = QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)
            names = {geo.LAYER_PARCEL: "قطع المخطط التنظيمي", geo.LAYER_ROAD: "شوارع تنظيمية",
                     geo.LAYER_WADI: "أودية ومجاري مياه"}
            for ds in g.datasets:
                for i, r in enumerate(ds.bbox):
                    if not r.intersects(box):
                        continue
                    layer = names.get(ds.layers[i], "قطع المخطط التنظيمي")
                    closed = ds.layers[i] == geo.LAYER_PARCEL
                    for part, cl in _clip(ds, i, box, closed):
                        wr.poly(layer, [(x + g.ox, y + g.oy) for x, y in part], close=cl)
                    if closed and ds.nums[i] and box.contains(r.center()):
                        c = r.center()
                        pos = (c.x() + g.ox, c.y() + g.oy)
                        msp.add_text(ds.nums[i], height=1.2, dxfattribs={"layer": layer, "insert": pos}) \
                            .set_placement(pos, align=TextEntityAlignment.MIDDLE_CENTER)
        except Exception:  # noqa: BLE001
            pass

    if path.get("parcelPts"):
        wr.poly("القطعة المحددة", path["parcelPts"], close=True)
        wr.label("القطعة المحددة", path["parcelPts"][:2], f"القطعة المحددة {path.get('parcel') or ''}", 1.5)

    w = float(path.get("w") or 6)
    for P in path.get("roads") or []:
        wr.poly("شارع", P, width=w)
        wr.label("شارع", P, f"شارع — {_length(P):.2f} م × {w:g} م", 1.5)
    for key, code in (("wallsR", "RD-005"), ("wallsC", "RD-006")):
        for P in path.get(key) or []:
            ln = wr.item_layer(code)
            wr.poly(ln, P, width=0.3)
            wr.label(ln, P, f"{ln} — {_length(P):.2f} م.ط")
    for code, gg in (path.get("items") or {}).items():
        ln = wr.item_layer(code)
        it = wr.items.get(code) or {}
        unit = gg.get("unit") or it.get("unit") or ""
        for P in gg.get("lines") or []:
            wr.poly(ln, P)
            wr.label(ln, P, f"{ln} — {_length(P):.2f} {unit}")
        for P in gg.get("polys") or []:
            wr.poly(ln, P, close=True)
            a = _area(P)
            if unit == "م³":
                dep = float(it.get("depth") or 0.3)
                txt = f"{ln} — {a * dep:.2f} م³ ({a:.1f} م² × {dep:g} م)"
            else:
                txt = f"{ln} — {a:.2f} م²"
            cx, cy = sum(q[0] for q in P) / len(P), sum(q[1] for q in P) / len(P)
            wr.label(ln, [(cx, cy)], txt)
        for q in gg.get("points") or []:
            msp.add_point(q, dxfattribs={"layer": ln})
            msp.add_circle(q, 0.5, dxfattribs={"layer": ln})
        if gg.get("points"):
            wr.label(ln, [gg["points"][0]], f"{ln} — {len(gg['points'])} عدد")

    # الصرف الصحي: القطع حسب حالتها ودخلات الخدمات المقترحة
    sew = path.get("sewer")
    if sew:
        status_layers = {"served": ("قطع مخدومة بالصرف", (3, "Continuous", 35)),
                         "deepen": ("قطع تحتاج تعميق خط الصرف", (40, "Continuous", 35)),
                         "lane": ("قطع تحتاج دخلة خدمات", (12, "Continuous", 50)),
                         "no_outlet": ("قطع بلا مصرف قريب", (200, "Continuous", 50))}
        lane_layer = wr._layer("دخلة خدمات", (6, "DASHED", 50))
        for lot in sew.get("lots") or []:
            if lot["status"] not in status_layers:
                continue
            name_l, style = status_layers[lot["status"]]
            ln = wr._layer(name_l, style)
            wr.poly(ln, lot["poly"], close=True)
            cx = sum(q[0] for q in lot["poly"]) / len(lot["poly"])
            cy = sum(q[1] for q in lot["poly"]) / len(lot["poly"])
            wr.label(ln, [(cx, cy)], f"{lot['num']} — {name_l}")
            lane = lot.get("lane")
            if lane:
                wr.poly(lane_layer, lane["path"], width=lane["width"])
                wr.label(lane_layer, lane["path"], f"دخلة خدمات {lane['width']:g} م — {lane['length']:.1f} م")

    # تجمع الأمطار والأودية المقترحة
    dr = path.get("drainage")
    if dr:
        l_sag = wr._layer("نقاط تجمع الأمطار", (5, "Continuous", 50))
        l_lane = wr._layer("دخلات تصريف الأمطار", (130, "DASHED", 50))
        l_wadi = wr._layer("أودية مقترحة", (150, "Continuous", 70))
        for n, sg in enumerate(dr.get("sags") or [], 1):
            msp.add_circle((sg["x"], sg["y"]), 1.5, dxfattribs={"layer": l_sag})
            wr.label(l_sag, [(sg["x"], sg["y"])], f"تجمع أمطار {n} — منسوب {sg['z']:.2f} — Q {sg['q']:.3f} م³/ث")
            if len(sg.get("path") or []) > 1:
                wr.poly(l_lane, sg["path"])
                wr.label(l_lane, sg["path"], f"دخلة تصريف إلى {sg['outlet']} — {sg['lane_len']:.0f} م")
        for wd in dr.get("wadis") or []:
            c = wd["channel"]
            wr.poly(l_wadi, wd["path"], width=c["width"])
            wr.label(l_wadi, wd["path"], f"وادٍ مقترح {c['width']:g}×{c['depth']:g} م — Q {wd['q']:.2f} م³/ث")

    anchor = (path.get("parcelPts") or pts or [[0, 0]])[0]
    note = msp.add_mtext(f"المواطن: {name}\\Pالقطعة: {path.get('parcel') or ''}\\P"
                         f"طول الشارع المحتسب: {path.get('bill', 0):.2f} م × {w:g} م",
                         dxfattribs={"layer": "ملاحظات", "style": "ARABIC", "char_height": 2.0})
    note.set_location((anchor[0], anchor[1] + 12), attachment_point=MTextEntityAlignment.BOTTOM_LEFT)
    wr.doc.saveas(out_file)
