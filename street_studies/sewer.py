"""فحص خدمة القطع بالصرف الصحي من جهة الشارع، واقتراح دخلات خدمات للقطع غير المخدومة.

لكل قطعة على الشارع:
- خط المجاري في محور الشارع: منسوب قاعه = المنسوب التصميمي للشارع (أو الأرض) − عمق الخط.
- الوصلة المنزلية تبدأ من أوطأ نقطة في القطعة بعمق محدد، وتنحدر بميل لا يقل عن الحد إلى خط الشارع.
- إن لم تصل بالجاذبية: نجرّب تعميق خط الشارع حتى أقصى عمق مسموح.
- إن تعذّر: نقترح دخلة خدمات من أوطأ نقطة إلى أقرب مصرف أوطأ (شارع آخر، جزء أوطأ من نفس الشارع، أو وادٍ).
كل الإحداثيات مطلقة (JTM).
"""
import math

DEFAULTS = {
    "sewer_depth": 1.8,      # عمق قاع خط الشارع تحت منسوب الشارع (م)
    "max_depth": 4.5,        # أقصى عمق مسموح لخط الشارع (م)
    "conn_slope": 0.02,      # أقل ميل للوصلة المنزلية
    "start_depth": 0.6,      # عمق بداية الوصلة عند أوطأ نقطة في القطعة (م)
    "lane_width": 4.0,       # عرض دخلة الخدمات المقترحة (م)
    "search_radius": 250.0,  # مدى البحث عن مصرف لدخلة الخدمات (م)
}

SERVED, DEEPEN, LANE, NO_OUTLET, NO_DATA = "served", "deepen", "lane", "no_outlet", "no_data"
STATUS_TEXT = {
    SERVED: "مخدومة من الشارع",
    DEEPEN: "مخدومة بتعميق خط الشارع",
    LANE: "تحتاج دخلة خدمات",
    NO_OUTLET: "غير مخدومة — لا يوجد مصرف أوطأ قريب",
    NO_DATA: "خارج منطقة الكنتور",
}


# ---------------------------------------------------------------- أدوات
def _nearest_on(P, x, y):
    """أقرب نقطة على خط متعدد: (المسافة، x، y، المسافة على طول الخط)."""
    best = (math.inf, x, y, 0.0)
    s0 = 0.0
    for i in range(1, len(P)):
        (x1, y1), (x2, y2) = P[i - 1][:2], P[i][:2]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        L = math.sqrt(L2)
        t = 0.0 if not L2 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        px, py = x1 + t * dx, y1 + t * dy
        d = math.hypot(x - px, y - py)
        if d < best[0]:
            best = (d, px, py, s0 + t * L)
        s0 += L
    return best


def _inside(P, x, y):
    c = False
    j = len(P) - 1
    for i in range(len(P)):
        xi, yi = P[i][:2]
        xj, yj = P[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def _densify(P, step):
    out = []
    for i in range(1, len(P)):
        (x1, y1), (x2, y2) = P[i - 1][:2], P[i][:2]
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / step))
        out += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n)]
    out.append(tuple(P[-1][:2]))
    return out


def _road_level(road, prof, s):
    """منسوب الشارع عند المسافة s: التصميمي إن وُجد بروفايل، وإلا الأرض."""
    if not prof:
        return None
    st = prof["stations"]
    if s <= st[0]["s"]:
        return st[0]["zd"]
    for a, b in zip(st, st[1:]):
        if a["s"] <= s <= b["s"]:
            t = (s - a["s"]) / (b["s"] - a["s"]) if b["s"] > a["s"] else 0
            return a["zd"] + (b["zd"] - a["zd"]) * t
    return st[-1]["zd"]


def lowest_point(poly, terrain, spacing=4.0, max_pts=600):
    """أوطأ نقطة في القطعة (من رؤوسها ونقاط شبكة داخلها)."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    area_w, area_h = max(xs) - min(xs), max(ys) - min(ys)
    sp = max(spacing, math.sqrt(max(area_w * area_h, 1) / max_pts))
    pts = list(_densify(poly, sp))
    y = min(ys) + sp / 2
    while y < max(ys):
        x = min(xs) + sp / 2
        while x < max(xs):
            if _inside(poly, x, y):
                pts.append((x, y))
            x += sp
        y += sp
    best = None
    covered = 0
    for x, y in pts:
        z = terrain.elevation(x, y)
        if z is None:
            continue
        covered += 1
        if best is None or z < best[2]:
            best = (x, y, z)
    return best, covered / max(len(pts), 1)


# ---------------------------------------------------------------- التحليل
def frontage_lots(roads, width, datasets, ox, oy, extra=None, tol=2.5):
    """القطع المطلة على الشارع من المخطط التنظيمي: [{'num', 'poly', 'front': [(x,y)...]}] بإحداثيات مطلقة."""
    from . import geo
    half = width / 2 + tol
    lots = {}
    for ds in datasets:
        for P in roads:
            xs, ys = [p[0] - ox for p in P], [p[1] - oy for p in P]
            cand = set()
            for x, y in _densify([(a, b) for a, b in zip(xs, ys)], geo.CELL / 2):
                cand |= ds.candidates(x, y, half)
            for i in cand:
                if ds.layers[i] != geo.LAYER_PARCEL:
                    continue
                poly = ds.abs_points(i)
                if len(poly) < 3:
                    continue
                front = [q for q in _densify(poly, 1.0) if _nearest_on(P, q[0], q[1])[0] <= half]
                if len(front) < 2:
                    continue
                key = (id(ds), i)
                lot = lots.setdefault(key, {"num": ds.nums[i] or "—", "poly": poly, "front": []})
                lot["front"] += front
    out = list(lots.values())
    for e in extra or []:   # قطع إضافية (مثل الإفراز لاحقاً)
        out.append(e)
    return out


def analyze(roads, width, terrain, lots, profiles=None, outlets=None, **opts):
    """roads: خطوط الشارع (مطلقة). profiles: نتيجة profile.compute_all أو None.
    outlets: [(النوع، خط مطلق، تسمية)] مصارف محتملة لدخلات الخدمات ('road' أو 'wadi')."""
    o = dict(DEFAULTS, **{k: v for k, v in opts.items() if v is not None})
    profs = (profiles or {}).get("roads") or [None] * len(roads)
    results = []
    for lot in lots:
        low, cover = lowest_point(lot["poly"], terrain)
        r = {"num": lot["num"], "poly": lot["poly"]}
        if low is None or cover < 0.5:
            r.update(status=NO_DATA)
            results.append(r)
            continue
        lx, ly, lz = low
        r["low"] = [round(lx, 2), round(ly, 2), round(lz, 2)]
        # أقرب نقطة على الواجهة إلى أوطأ نقطة، ثم إسقاطها على محور الشارع
        fx, fy = min(lot["front"], key=lambda q: math.hypot(q[0] - lx, q[1] - ly))
        best_road = min(range(len(roads)), key=lambda k: _nearest_on(roads[k], fx, fy)[0])
        d_axis, ax, ay, s = _nearest_on(roads[best_road], fx, fy)
        level = _road_level(roads[best_road], profs[best_road] if best_road < len(profs) else None, s)
        if level is None:
            level = terrain.elevation(ax, ay)
        if level is None:
            r.update(status=NO_DATA)
            results.append(r)
            continue
        conn = math.hypot(fx - lx, fy - ly) + d_axis
        start = lz - o["start_depth"]
        arrive = start - o["conn_slope"] * conn          # منسوب وصول الوصلة إلى المحور
        invert = level - o["sewer_depth"]
        r.update(front=[round(fx, 2), round(fy, 2)], road_level=round(level, 2), invert=round(invert, 2),
                 conn_len=round(conn, 1), arrive=round(arrive, 2))
        if arrive >= invert:
            r["status"] = SERVED
        elif arrive >= level - o["max_depth"]:
            r.update(status=DEEPEN, needed_depth=round(level - arrive, 2))
        else:
            lane = _find_lane((lx, ly, start), outlets or [], terrain, o)
            if lane:
                r.update(status=LANE, lane=lane)
            else:
                r["status"] = NO_OUTLET
        results.append(r)
    counts = {k: sum(1 for x in results if x["status"] == k) for k in STATUS_TEXT}
    return {"lots": results, "counts": counts, "params": o}


def _find_lane(start, outlets, terrain, o):
    """أقصر دخلة من بداية الوصلة إلى مصرف يستقبل بالجاذبية (مع السماح بتعميقه حتى الحد الأقصى)."""
    sx, sy, sz = start
    best = None
    for kind, P, name in outlets:
        for x, y in _densify(P, 5.0):
            L = math.hypot(x - sx, y - sy)
            if L > o["search_radius"] or L < 3:
                continue
            g = terrain.elevation(x, y)
            if g is None:
                continue
            arrive = sz - o["conn_slope"] * L
            depth_ok = g - o["sewer_depth"] if kind == "road" else g - 0.5
            depth_max = g - o["max_depth"] if kind == "road" else g - 1.5
            if arrive >= depth_max and (best is None or L < best["length"]):
                best = {"to": [round(x, 2), round(y, 2)], "length": round(L, 1), "kind": kind, "name": name,
                        "width": o["lane_width"], "outlet_ground": round(g, 2),
                        "deepen": arrive < depth_ok,
                        "path": [[round(sx, 2), round(sy, 2)], [round(x, 2), round(y, 2)]]}
    return best
