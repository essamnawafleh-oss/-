"""البروفايل الطولي للشارع: ميل الأرض لكل مقطع، المنسوب التصميمي، وكميات الحفر والردم.

المنسوب التصميمي يُختار بالبرمجة الديناميكية بحيث يكون أقرب ما يمكن لسطح الأرض (أقل حفر وردم)
مع شرطين: الميل في أي مقطع ≤ الحد (19%)، والقطع/الردم على واجهتي الشارع (حدود القطع) ≤ الحد (4 م).
إذا تعذّر تحقيق الشرطين معاً في مكان ما، يُعطى أفضل حل ممكن وتُحدَّد المقاطع المخالفة.
"""
import math

DEFAULTS = {"max_grade": 0.19, "max_cutfill": 4.0, "step": 5.0, "cut_slope": 1.0, "fill_slope": 1.5}
_DZ = 0.1               # دقة البحث في المنسوب التصميمي (م)
_PEN_CF = 100.0         # عقوبة كل متر يتجاوز حد القطع/الردم
_PEN_GRADE = 1000.0     # عقوبة كل متر يتجاوز حد الميل


def _stations(P, step):
    """نقاط كل step متر على طول المسار (مع رؤوس المسار)، مع اتجاه العمود عند كل نقطة."""
    out = []
    s0 = 0.0
    for i in range(1, len(P)):
        (x1, y1), (x2, y2) = P[i - 1][:2], P[i][:2]
        L = math.hypot(x2 - x1, y2 - y1)
        if L <= 0:
            continue
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        n = max(1, math.ceil(L / step))
        for k in range(n):
            t = k / n
            out.append((s0 + L * t, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, -uy, ux))
        s0 += L
    (xa, ya), (xb, yb) = P[-2][:2], P[-1][:2]
    L = math.hypot(xb - xa, yb - ya) or 1
    out.append((s0, xb, yb, -(yb - ya) / L, (xb - xa) / L))
    return out


def _half_area(z0, z1, zd, half):
    """مساحة الحفر والردم على نصف عرض الشارع بأرض خطية من z0 (المحور) إلى z1 (الحافة)."""
    a, b = z0 - zd, z1 - zd
    if a >= 0 and b >= 0:
        return (a + b) / 2 * half, 0.0
    if a <= 0 and b <= 0:
        return 0.0, -(a + b) / 2 * half
    t = a / (a - b)           # نقطة التقاطع مع المنسوب التصميمي
    pos, neg = (a, b) if a > 0 else (b, a)
    frac = t if a > 0 else 1 - t
    return pos * frac * half / 2, -neg * (1 - frac) * half / 2


def compute(P, width, terrain, **opts):
    o = dict(DEFAULTS, **{k: v for k, v in opts.items() if v is not None})
    gmax, cfmax, step = o["max_grade"], o["max_cutfill"], o["step"]
    half = width / 2
    st = []
    for s, x, y, nx, ny in _stations(P, step):
        zc = terrain.elevation(x, y)
        zl = terrain.elevation(x + nx * half, y + ny * half)
        zr = terrain.elevation(x - nx * half, y - ny * half)
        st.append({"s": s, "x": x, "y": y, "zc": zc, "zl": zl, "zr": zr})
    known = [p for p in st if p["zc"] is not None]
    if len(known) < 2:
        raise ValueError("مسار الشارع خارج منطقة الكنتور المرفق")
    missing = len(st) - len(known)
    st = known
    for p in st:   # حافة بلا منسوب ← نستخدم منسوب المحور
        p["zl"] = p["zl"] if p["zl"] is not None else p["zc"]
        p["zr"] = p["zr"] if p["zr"] is not None else p["zc"]

    # --- المنسوب التصميمي (برمجة ديناميكية)
    cands = []
    for p in st:
        lo = min(p["zc"], p["zl"], p["zr"]) - cfmax - 2
        hi = max(p["zc"], p["zl"], p["zr"]) + cfmax + 2
        n = int((hi - lo) / _DZ) + 1
        zs = [lo + k * _DZ for k in range(n)]
        cost = []
        for z in zs:
            c = abs(z - p["zc"])
            c += _PEN_CF * (max(0.0, abs(z - p["zl"]) - cfmax) + max(0.0, abs(z - p["zr"]) - cfmax))
            cost.append(c)
        cands.append((zs, cost))
    best = list(cands[0][1])
    back = [None]
    for i in range(1, len(st)):
        ds = st[i]["s"] - st[i - 1]["s"]
        zs_prev, _ = cands[i - 1]
        zs, cost = cands[i]
        reach = gmax * ds + 1.5
        nb, bk = [], []
        j0 = 0
        for z, c in zip(zs, cost):
            bv, bj = math.inf, -1
            # المرشحون السابقون ضمن مدى معقول فقط
            while j0 < len(zs_prev) and zs_prev[j0] < z - reach:
                j0 += 1
            j = j0
            while j < len(zs_prev) and zs_prev[j] <= z + reach:
                g = abs(z - zs_prev[j]) / ds if ds > 0 else 0
                v = best[j] + _PEN_GRADE * max(0.0, g - gmax) * ds
                if v < bv:
                    bv, bj = v, j
                j += 1
            if bj < 0:   # لا يوجد سابق ضمن المدى: نصل لأقرب واحد مع العقوبة
                bj = min(range(len(zs_prev)), key=lambda k: abs(zs_prev[k] - z))
                g = abs(z - zs_prev[bj]) / ds if ds > 0 else 0
                bv = best[bj] + _PEN_GRADE * max(0.0, g - gmax) * ds
            nb.append(bv + c)
            bk.append(bj)
        best = nb
        back.append(bk)
    k = min(range(len(best)), key=lambda q: best[q])
    zd = [0.0] * len(st)
    for i in range(len(st) - 1, -1, -1):
        zd[i] = cands[i][0][k]
        if i:
            k = back[i][k]
    for p, z in zip(st, zd):
        p["zd"] = round(z, 2)

    # --- الميول والمخالفات
    segs = []
    for a, b in zip(st, st[1:]):
        ds = b["s"] - a["s"]
        if ds <= 0:
            continue
        segs.append({"s0": a["s"], "s1": b["s"], "g_ground": (b["zc"] - a["zc"]) / ds,
                     "g_design": (b["zd"] - a["zd"]) / ds})
    tol = 0.005
    for p in st:
        p["cut_l"], p["cut_r"] = round(p["zl"] - p["zd"], 2), round(p["zr"] - p["zd"], 2)
        p["bad_cf"] = max(abs(p["cut_l"]), abs(p["cut_r"])) > cfmax + 0.05

    # --- الحفر والردم (متوسط المساحات بين المقطعين)
    def areas(p):
        c1, f1 = _half_area(p["zc"], p["zl"], p["zd"], half)
        c2, f2 = _half_area(p["zc"], p["zr"], p["zd"], half)
        cut, fill = c1 + c2, f1 + f2
        for e in (p["zl"], p["zr"]):    # الميول الجانبية خارج حدود الشارع
            h = e - p["zd"]
            if h > 0:
                cut += 0.5 * h * h * o["cut_slope"]
            else:
                fill += 0.5 * h * h * o["fill_slope"]
        return cut, fill
    A = [areas(p) for p in st]
    cut_v = sum((A[i][0] + A[i + 1][0]) / 2 * (st[i + 1]["s"] - st[i]["s"]) for i in range(len(st) - 1))
    fill_v = sum((A[i][1] + A[i + 1][1]) / 2 * (st[i + 1]["s"] - st[i]["s"]) for i in range(len(st) - 1))

    # هل يمكن أصلاً تحقيق حد الميل على هذا المسار؟ (فرق منسوب الطرفين بعد الاستفادة من القطع/الردم المسموح)
    rise = abs(st[-1]["zc"] - st[0]["zc"])
    need = max(0.0, rise - 2 * cfmax) / gmax if gmax > 0 else 0.0
    length = st[-1]["s"] - st[0]["s"]
    return {
        "overall_grade": round(rise / length, 4) if length else 0.0,
        "min_length_needed": round(need, 1),
        "alignment_impossible": need > length + 1,
        "stations": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in p.items()} for p in st],
        "segments": [{k: round(v, 4) for k, v in g.items()} for g in segs],
        "length": round(st[-1]["s"] - st[0]["s"], 2),
        "max_ground_grade": round(max((abs(g["g_ground"]) for g in segs), default=0), 4),
        "max_design_grade": round(max((abs(g["g_design"]) for g in segs), default=0), 4),
        "ground_over": sum(1 for g in segs if abs(g["g_ground"]) > gmax + tol),
        "design_over": sum(1 for g in segs if abs(g["g_design"]) > gmax + tol),
        "cf_over": sum(1 for p in st if p["bad_cf"]),
        "max_cut": round(max((max(p["cut_l"], p["cut_r"], 0) for p in st), default=0), 2),
        "max_fill": round(max((max(-p["cut_l"], -p["cut_r"], 0) for p in st), default=0), 2),
        "cut": round(cut_v, 2), "fill": round(fill_v, 2), "missing": missing,
        "params": {"max_grade": gmax, "max_cutfill": cfmax, "step": step, "width": width},
    }


def compute_all(roads, width, terrain, **opts):
    """بروفايل لكل خط شارع، مع مجموع الحفر والردم."""
    out = [compute(P, width, terrain, **opts) for P in roads if len(P) >= 2]
    return {"roads": out, "cut": round(sum(r["cut"] for r in out), 2), "fill": round(sum(r["fill"] for r in out), 2),
            "ok": all(r["design_over"] == 0 and r["cf_over"] == 0 for r in out)}
