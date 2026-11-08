"""الإفراز: اقتراح تقسيم قطعة إلى قطع حسب الواجهة الدنيا والمساحة الدنيا، وفحص كل قطعة.

العمل في إطار محلي: المحور u موازٍ للشارع، والمحور v عمودي عليه نحو داخل القطعة.
- صف أمامي يطل على الشارع، يُقسَّم بخطوط عمودية على الشارع إلى قطع متساوية المساحة.
- إن كانت القطعة عميقة: شارع داخلي موازٍ للشارع مع شارع وصول من أحد الطرفين، وصف خلفي يطل على الشارع الداخلي.
- الفحص لكل قطعة: المساحة، الواجهة، العمق، والصرف الصحي؛ وللشارع الداخلي: الميل والقطع/الردم.
كل الإحداثيات مطلقة (JTM).
"""
import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPolygonF

DEFAULTS = {
    "min_area": 500.0,       # أقل مساحة للقطعة (م²) — من أحكام التنظيم إن وُجدت
    "min_frontage": 18.0,    # أقل واجهة أمامية (م)
    "internal_road": True,   # شارع داخلي للقطع العميقة
    "road_width": 8.0,       # عرض الشارع الداخلي وشارع الوصول (م)
    "front_depth": 30.0,     # عمق الصف الأمامي عند وجود شارع داخلي (م)
}


# ---------------------------------------------------------------- إطار محلي
class Frame:
    def __init__(self, road, poly):
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        # أقرب ضلع من الشارع إلى مركز القطعة يحدد الاتجاه
        best = None
        for a, b in zip(road, road[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            if not L2:
                continue
            t = max(0.0, min(1.0, ((cx - a[0]) * dx + (cy - a[1]) * dy) / L2))
            d = math.hypot(cx - a[0] - t * dx, cy - a[1] - t * dy)
            if best is None or d < best[0]:
                best = (d, a, b, t)
        _, a, b, t = best
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        self.ux, self.uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        self.ox, self.oy = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        # المحور v نحو داخل القطعة
        self.vx, self.vy = -self.uy, self.ux
        if (cx - self.ox) * self.vx + (cy - self.oy) * self.vy < 0:
            self.vx, self.vy = -self.vx, -self.vy

    def to_local(self, x, y):
        dx, dy = x - self.ox, y - self.oy
        return dx * self.ux + dy * self.uy, dx * self.vx + dy * self.vy

    def to_world(self, u, v):
        return self.ox + u * self.ux + v * self.vx, self.oy + u * self.uy + v * self.vy


def _qpoly(pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _pts(q):
    out = [(q.at(k).x(), q.at(k).y()) for k in range(q.size())]
    if len(out) > 1 and math.dist(out[0], out[-1]) < 1e-6:
        out.pop()
    return out


def _area(P):
    if len(P) < 3:
        return 0.0
    return abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))) / 2


def _rect(u0, u1, v0, v1):
    return _qpoly([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])


def _clip(poly_q, u0, u1, v0, v1):
    return poly_q.intersected(_rect(u0, u1, v0, v1))


def _split_equal(region_q, n, u0, u1):
    """تقسيم منطقة إلى n شرائح متساوية المساحة بخطوط عمودية (u ثابت)."""
    total = _area(_pts(region_q))
    cuts = [u0]
    for k in range(1, n):
        target = total * k / n
        lo, hi = cuts[-1], u1
        for _ in range(40):
            mid = (lo + hi) / 2
            a = _area(_pts(_clip(region_q, u0 - 1, mid, -1e6, 1e6)))
            if a < target:
                lo = mid
            else:
                hi = mid
        cuts.append((lo + hi) / 2)
    cuts.append(u1)
    strips = []
    for a, b in zip(cuts, cuts[1:]):
        q = _clip(region_q, a - (1 if a == u0 else 0), b + (1 if b == u1 else 0), -1e6, 1e6)
        P = _pts(q)
        if len(P) >= 3:
            strips.append(P)
    return strips


def frontage_length(P, lines, tol):
    """طول حدود القطعة الواقعة ضمن tol من أي خط (محور شارع)."""
    total = 0.0
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        L = math.dist(a, b)
        if L <= 0:
            continue
        n = max(2, int(L / 0.5))
        hits = 0
        for k in range(n):
            t = (k + .5) / n
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if any(_dist_line(L_, x, y) <= tol for L_ in lines):
                hits += 1
        total += L * hits / n
    return total


def _dist_line(P, x, y):
    best = math.inf
    for a, b in zip(P, P[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if not L2 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L2))
        best = min(best, math.hypot(x - a[0] - t * dx, y - a[1] - t * dy))
    return best


# ---------------------------------------------------------------- الاقتراح التلقائي
def _row_lots(region_q, u0, u1, min_area, min_front, front_lines, tol):
    """تقسيم صف على طول الشارع: كل قطعة تأخذ أقل عرض يحقق الواجهة والمساحة الدنيا، ثم تبدأ التالية.
    الباقي الأخير يُضم للقطعة السابقة إن كان أصغر من الحد."""
    lots = []
    start = u0
    step = 0.5
    while start < u1 - 0.5:
        u = start + max(1.0, min_front * 0.5)
        found = None
        while u <= u1 + 1e-6:
            q = _clip(region_q, start - (1 if start == u0 else 0), u, -1e6, 1e6)
            P = _pts(q)
            if len(P) >= 3 and _area(P) >= min_area and frontage_length(P, front_lines, tol) >= min_front:
                found = (u, P)
                break
            u += step
        if not found:
            # الباقي لا يكفي قطعة مستقلة: يُضم لآخر قطعة
            if lots:
                q = _clip(region_q, lots[-1][0], u1 + 1, -1e6, 1e6)
                lots[-1] = (lots[-1][0], _pts(q))
            break
        lots.append((start, found[1]))
        start = found[0]
    if lots:   # آخر قطعة تمتد حتى نهاية الصف
        q = _clip(region_q, lots[-1][0] - (1 if lots[-1][0] == u0 else 0), u1 + 1, -1e6, 1e6)
        lots[-1] = (lots[-1][0], _pts(q))
    return [P for _, P in lots if len(P) >= 3]


def propose(parcel, road, main_width, **opts):
    """parcel: مضلع القطعة (مطلق). road: محور الشارع الذي تطل عليه (مطلق).
    يرجع {'lots': [مضلعات مطلقة], 'roads': [محاور الشوارع الداخلية], 'road_polys': [...]}."""
    o = dict(DEFAULTS, **{k: v for k, v in opts.items() if v is not None})
    f = Frame(road, parcel)
    loc = [f.to_local(x, y) for x, y in parcel]
    pq = _qpoly(loc)
    us, vs = [p[0] for p in loc], [p[1] for p in loc]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    main_axis = [(u0 - 50, 0.0), (u1 + 50, 0.0)]      # محور الشارع في الإطار المحلي (v = 0)
    tol_main = main_width / 2 + 2.5
    rw, fd = o["road_width"], o["front_depth"]
    depth = v1 - v0
    out = {"roads": [], "road_polys": [], "lots": [], "frame_depth": round(depth, 1)}
    if not o["internal_road"] or depth <= fd * 2 + rw + 5:
        strips = _row_lots(pq, u0, u1, o["min_area"], o["min_frontage"], [main_axis], tol_main)
        out["lots"] = [[f.to_world(u, v) for u, v in P] for P in strips]
        return out

    # صفوف: صف أمامي على الشارع، ثم [شارع داخلي، صف يطل عليه من كل جهة] بالتكرار
    tol_int = rw / 2 + 1.0
    # شارع الوصول: أول موضع على طول الواجهة تغطيه القطعة من الشارع حتى عمق الشارع الداخلي الأول
    need_v = v0 + fd + rw
    ua0 = u0
    u = u0
    while u < u1 - rw:
        strip = _pts(_clip(pq, u, u + rw, v0 - 1, need_v))
        if strip and min(p[1] for p in strip) <= v0 + 2 and max(p[1] for p in strip) >= need_v - 0.5 and \
                _area(strip) >= rw * (need_v - v0) * 0.9:
            ua0 = u
            break
        u += 1.0
    ua1 = ua0 + rw
    rows = [(v0 - 1, v0 + fd, ua1, "main")]            # (من v، إلى v، بداية u، يطل على)
    bands = []
    v = v0 + fd
    while v1 - v > fd * 0.75:
        b0, b1 = v, v + rw
        bands.append((b0, b1))
        r1_end = min(b1 + fd, v1 + 1)
        rows.append((b1, r1_end, ua1 if r1_end < v1 - fd * 0.75 else u0, len(bands) - 1))
        v = r1_end
        if v1 - v <= fd * 0.75:
            break
        r2_end = v + fd
        if v1 - r2_end <= fd * 0.75 + rw:   # لا مكان لشارع آخر: الصف الأخير يأخذ الباقي
            rows.append((v, v1 + 1, u0, len(bands) - 1))
            v = v1
            break
        rows.append((v, r2_end, ua1, len(bands)))   # يطل على الشارع التالي
        v = r2_end
    band_axes = []
    for b0, b1 in bands:
        # محور الشارع مقصوص على امتداد القطعة عند منتصف الشريط
        mid = _pts(_clip(pq, u0 - 1, u1 + 1, (b0 + b1) / 2 - 0.25, (b0 + b1) / 2 + 0.25))
        ub0 = min(p[0] for p in mid) if mid else u0
        ub1 = max(p[0] for p in mid) if mid else u1
        band_axes.append([(ub0, (b0 + b1) / 2), (ub1, (b0 + b1) / 2)])
    last_band = bands[-1][1] if bands else v0
    acc = _pts(_clip(pq, ua0 + rw / 2 - 0.25, ua0 + rw / 2 + 0.25, v0 - 1, last_band))
    va0 = min(p[1] for p in acc) if acc else v0
    access_axis = [(ua0 + rw / 2, min(va0, v0 + 0.5)),
                   (ua0 + rw / 2, (bands[-1][0] + bands[-1][1]) / 2 if bands else v0)]
    lots = []
    for a, b, us0, faces in rows:
        if faces == "main":
            lines, tol = [main_axis, access_axis], max(tol_main, tol_int)
        else:
            k = min(faces, len(band_axes) - 1)
            lines, tol = [band_axes[k], access_axis], tol_int
        # الصفوف التي يقطعها شارع الوصول تُقسَّم على جهتيه
        spans = [(u0, ua0), (ua1, u1)] if us0 == ua1 else [(u0, u1)]
        for s0, s1 in spans:
            if s1 - s0 < 1:
                continue
            region = _clip(pq, s0 - (1 if s0 == u0 else 0), s1 + (1 if s1 == u1 else 0), a, b)
            if region.size() < 3:
                continue
            lots += _row_lots(region, s0, s1, o["min_area"], o["min_frontage"], lines, tol)
    out["lots"] = [[f.to_world(u, v) for u, v in P] for P in lots]
    out["roads"] = [[f.to_world(u, v) for u, v in access_axis]] + \
                   [[f.to_world(u, v) for u, v in ax] for ax in band_axes]
    polys = [_clip(pq, ua0, ua1, v0 - 1, last_band)] + [_clip(pq, u0 - 1, u1 + 1, b0, b1) for b0, b1 in bands]
    out["road_polys"] = [[f.to_world(u, v) for u, v in _pts(q)] for q in polys if q.size() > 2]
    return out


# ---------------------------------------------------------------- الفحص
def check(lots, roads, main_width, internal_width, terrain=None, **opts):
    """فحص قطع الإفراز (مقترحة أو مرسومة). roads: الشارع الرئيسي، internal: الشوارع الداخلية."""
    from . import profile, sewer
    o = dict(DEFAULTS, **{k: v for k, v in opts.items() if v is not None})
    main_roads, int_roads = roads
    all_lines = [(P, main_width / 2 + 2.5) for P in main_roads] + [(P, internal_width / 2 + 1.0) for P in int_roads]
    results = []
    for n, P in enumerate(lots, 1):
        area = _area(P)
        front = sum(frontage_length(P, [L], tol) for L, tol in all_lines)
        reasons = []
        if area < o["min_area"] * 0.999:
            reasons.append(f"المساحة أقل من {o['min_area']:g} م²")
        if front < o["min_frontage"] * 0.98:
            reasons.append("لا تطل على شارع" if front < 0.5 else f"الواجهة أقل من {o['min_frontage']:g} م")
        results.append({"n": n, "poly": [[round(x, 2), round(y, 2)] for x, y in P], "area": round(area, 1),
                        "frontage": round(front, 1), "reasons": reasons})
    out = {"lots": results, "params": o, "internal": [], "sewer": None}
    if terrain is not None:
        # بروفايل الشوارع الداخلية (الميل والقطع/الردم)
        for P in int_roads:
            try:
                pr = profile.compute(P, internal_width, terrain)
                out["internal"].append({"path": [[round(x, 2), round(y, 2)] for x, y in P], "profile": pr})
                if pr["design_over"] or pr["cf_over"]:
                    pass
            except ValueError:
                out["internal"].append({"path": [[round(x, 2), round(y, 2)] for x, y in P], "profile": None})
        # الصرف الصحي لكل قطعة من الشارع الذي تطل عليه
        lot_entries = []
        for r in results:
            pts = [tuple(q) for q in r["poly"]]
            front_pts = [q for q in sewer._densify(pts + pts[:1], 1.0)
                         if any(_dist_line(L, q[0], q[1]) <= tol for L, tol in all_lines)]
            if len(front_pts) >= 2:
                lot_entries.append({"num": str(r["n"]), "poly": pts, "front": front_pts})
        if lot_entries:
            sew = sewer.analyze(main_roads + int_roads, max(main_width, internal_width), terrain, lot_entries,
                                None, [("road", P, "شارع") for P in main_roads + int_roads])
            by = {x["num"]: x for x in sew["lots"]}
            for r in results:
                s = by.get(str(r["n"]))
                if s:
                    r["sewer"] = s["status"]
                    if s["status"] in (sewer.LANE, sewer.NO_OUTLET):
                        r["reasons"].append("غير مخدومة بالصرف من الشارع")
            out["sewer"] = sew
    out["ok"] = sum(1 for r in results if not r["reasons"])
    return out
