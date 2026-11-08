"""تجمع مياه الأمطار على الشارع، ومسارات تصريفها، والأودية المقترحة من خطوط الكنتور.

1) نموذج ارتفاعات شبكي (DEM) من الكنتور، مع ملء المنخفضات الوهمية، ثم اتجاه الجريان (D8) والمساحة الصابة لكل خلية.
2) نقاط تجمع الأمطار: أوطأ النقاط على البروفايل الطولي للشارع (التصميمي إن وُجد).
3) لكل نقطة تجمع: مسار جريان نحو الأسفل حتى أقرب وادٍ أو شارع آخر — يُقترح عليه «دخلة تصريف».
4) الأودية المقترحة: الخلايا التي تتجاوز مساحتها الصابة حداً معيناً، ولكل وادٍ مقطع ثابت مناسب
   محسوب من أقصى تدفق عند مصبه (الطريقة العقلانية Q = 0.278·C·i·A) ومعادلة ماننغ.
كل الإحداثيات مطلقة (JTM).
"""
import heapq
import math

DEFAULTS = {
    "runoff_c": 0.6,         # معامل الجريان السطحي
    "intensity": 50.0,       # شدة المطر التصميمية (مم/ساعة)
    "stream_ha": 2.0,        # أقل مساحة صابة لبدء وادٍ (هكتار)
    "manning_n": 0.015,      # معامل ماننغ (قناة خرسانية)
    "freeboard": 0.2,        # نسبة الارتفاع الحر فوق عمق الجريان
    "max_cells": 20000,      # حد عدد خلايا النموذج (للسرعة)
    "margin": 250.0,         # المنطقة المدروسة حول الشارع (م)
    "max_velocity": 4.0,     # أقصى سرعة مقبولة في القناة (م/ث) — فوقها تلزم مساقط لتكسير الطاقة
}
_D8 = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
STANDARD_WIDTHS = [0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]


class Grid:
    def __init__(self, terrain, box, max_cells):
        x0, y0, x1, y1 = box
        tx0, ty0, tx1, ty1 = terrain.bounds
        x0, y0, x1, y1 = max(x0, tx0), max(y0, ty0), min(x1, tx1), min(y1, ty1)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("الشارع خارج منطقة الكنتور المرفق")
        self.cell = max(4.0, math.sqrt((x1 - x0) * (y1 - y0) / max_cells))
        self.x0, self.y0 = x0, y0
        self.nx = max(2, int((x1 - x0) / self.cell) + 1)
        self.ny = max(2, int((y1 - y0) / self.cell) + 1)
        self.z = [[None] * self.nx for _ in range(self.ny)]
        for j in range(self.ny):
            y = y0 + j * self.cell
            for i in range(self.nx):
                self.z[j][i] = terrain.elevation(x0 + i * self.cell, y)

    def xy(self, i, j):
        return self.x0 + i * self.cell, self.y0 + j * self.cell

    def ij(self, x, y):
        return (max(0, min(self.nx - 1, round((x - self.x0) / self.cell))),
                max(0, min(self.ny - 1, round((y - self.y0) / self.cell))))

    def valid(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.ny and self.z[j][i] is not None


def _fill_and_flow(g):
    """ملء المنخفضات (priority-flood) ثم اتجاه الجريان D8 والمساحة الصابة (م²)."""
    nx, ny = g.nx, g.ny
    filled = [[None] * nx for _ in range(ny)]
    done = [[False] * nx for _ in range(ny)]
    heap = []
    for j in range(ny):
        for i in range(nx):
            if g.z[j][i] is None:
                continue
            edge = i in (0, nx - 1) or j in (0, ny - 1) or any(
                not g.valid(i + di, j + dj) for di, dj in _D8)
            if edge:
                heapq.heappush(heap, (g.z[j][i], i, j))
                done[j][i] = True
                filled[j][i] = g.z[j][i]
    eps = 1e-4
    while heap:
        z, i, j = heapq.heappop(heap)
        for di, dj in _D8:
            a, b = i + di, j + dj
            if g.valid(a, b) and not done[b][a]:
                done[b][a] = True
                filled[b][a] = max(g.z[b][a], z + eps)
                heapq.heappush(heap, (filled[b][a], a, b))
    # اتجاه الجريان: أشد انحدار
    down = [[None] * nx for _ in range(ny)]
    order = []
    for j in range(ny):
        for i in range(nx):
            if filled[j][i] is None:
                continue
            order.append((filled[j][i], i, j))
            best, bs = None, 0.0
            for di, dj in _D8:
                a, b = i + di, j + dj
                if 0 <= a < nx and 0 <= b < ny and filled[b][a] is not None:
                    s = (filled[j][i] - filled[b][a]) / math.hypot(di, dj)
                    if s > bs:
                        best, bs = (a, b), s
            down[j][i] = best
    # المساحة الصابة: من الأعلى للأسفل
    cell_a = g.cell * g.cell
    acc = [[cell_a if filled[j][i] is not None else 0.0 for i in range(nx)] for j in range(ny)]
    for _, i, j in sorted(order, reverse=True):
        d = down[j][i]
        if d:
            acc[d[1]][d[0]] += acc[j][i]
    return filled, down, acc


def _sags(stations, key):
    """أوطأ النقاط على البروفايل (مع الطرفين إن كان الماء يجري نحوهما)."""
    z = [s[key] for s in stations]
    out = []
    n = len(z)
    for k in range(n):
        left = z[k - 1] if k > 0 else math.inf
        right = z[k + 1] if k < n - 1 else math.inf
        if z[k] <= left and z[k] <= right and not (left == math.inf and right == math.inf):
            out.append(k)
    merged = []
    for k in out:   # دمج النقاط المتقاربة (أقل من 15 م)
        if merged and stations[k]["s"] - stations[merged[-1]]["s"] < 15:
            if z[k] < z[merged[-1]]:
                merged[-1] = k
        else:
            merged.append(k)
    return merged


def _road_catchment(stations, key, k):
    """طول الشارع الذي يصرّف إلى نقطة التجمع k (بين القمتين المحيطتين)."""
    z = [s[key] for s in stations]
    a = k
    while a > 0 and z[a - 1] >= z[a]:
        a -= 1
    b = k
    while b < len(z) - 1 and z[b + 1] >= z[b]:
        b += 1
    return stations[b]["s"] - stations[a]["s"]


def _nearest_dist(P_list, x, y):
    best = math.inf
    for P in P_list:
        for i in range(1, len(P)):
            (x1, y1), (x2, y2) = P[i - 1][:2], P[i][:2]
            dx, dy = x2 - x1, y2 - y1
            L2 = dx * dx + dy * dy
            t = 0.0 if not L2 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
            best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
    return best


def peak_flow(area_m2, c, intensity):
    """الطريقة العقلانية: Q (م³/ث) = 0.278 · C · i (مم/س) · A (كم²)."""
    return 0.278 * c * intensity * area_m2 / 1e6


def size_channel(q, slope, n, freeboard, vmax=4.0):
    ch = _size_channel(q, slope, n, freeboard)
    ch["drops"] = ch["velocity"] > vmax   # السرعة عالية: يلزم مساقط/درجات لتكسير الطاقة
    return ch


def _size_channel(q, slope, n, freeboard):
    """أصغر قناة مستطيلة قياسية (العمق = نصف العرض تقريباً) تمرّر التدفق q عند الميل slope."""
    s = max(slope, 0.003)
    for b in STANDARD_WIDTHS:
        lo, hi = 0.0, b * 1.5
        for _ in range(40):   # عمق الجريان المطلوب (تنصيف)
            h = (lo + hi) / 2
            A, P = b * h, b + 2 * h
            cap = (1 / n) * A * (A / P) ** (2 / 3) * math.sqrt(s)
            if cap >= q:
                hi = h
            else:
                lo = h
        h = hi
        if h <= max(0.75 * b, 0.3):
            depth = math.ceil(h * (1 + freeboard) * 20) / 20
            return {"width": b, "depth": max(depth, 0.3), "flow_depth": round(h, 2),
                    "velocity": round(q / max(b * h, 1e-6), 2)}
    return {"width": STANDARD_WIDTHS[-1], "depth": round(h * (1 + freeboard), 2), "flow_depth": round(h, 2),
            "velocity": round(q / max(STANDARD_WIDTHS[-1] * h, 1e-6), 2), "oversize": True}


def analyze(roads, width, terrain, profiles=None, wadis=(), streets=(), **opts):
    """roads: خطوط الشارع (مطلقة). profiles: نتيجة البروفايل أو None.
    wadis/streets: خطوط الأودية والشوارع التنظيمية القريبة (مطلقة) كمصبات."""
    o = dict(DEFAULTS, **{k: v for k, v in opts.items() if v is not None})
    xs = [q[0] for P in roads for q in P]
    ys = [q[1] for P in roads for q in P]
    m = o["margin"]
    g = Grid(terrain, (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m), int(o["max_cells"]))
    filled, down, acc = _fill_and_flow(g)

    def trace(i, j, max_steps=4000):
        path = [(i, j)]
        seen = {(i, j)}
        while len(path) < max_steps:
            d = down[j][i]
            if d is None or d in seen:
                break
            i, j = d
            seen.add(d)
            path.append(d)
        return path

    # --- نقاط تجمع الأمطار على الشارع
    profs = (profiles or {}).get("roads") or []
    sags = []
    for r_i, P in enumerate(roads):
        prof = profs[r_i] if r_i < len(profs) else None
        if prof:
            st, key = prof["stations"], "zd"
        else:   # بدون بروفايل: منسوب الأرض كل 5 م
            st = []
            s0 = 0.0
            for a, b in zip(P, P[1:]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                n = max(1, int(L / 5))
                for k in range(n):
                    x, y = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
                    zc = terrain.elevation(x, y)
                    if zc is not None:
                        st.append({"s": s0 + L * k / n, "x": x, "y": y, "zc": zc})
                s0 += L
            key = "zc"
        if len(st) < 3:
            continue
        for k in _sags(st, key):
            p = st[k]
            i, j = g.ij(p["x"], p["y"])
            # المساحة الصابة: أكبر تراكم ضمن 15 م من النقطة + سطح الشارع المصرّف إليها
            rad = max(1, int(15 / g.cell))
            terr_a = max((acc[b][a] for a in range(i - rad, i + rad + 1) for b in range(j - rad, j + rad + 1)
                          if 0 <= a < g.nx and 0 <= b < g.ny), default=0.0)
            road_len = _road_catchment(st, key, k)
            area = terr_a + road_len * width
            q = peak_flow(area, o["runoff_c"], o["intensity"])
            # مسار الجريان حتى أول وادٍ أو شارع آخر
            path = trace(i, j)
            pts = [g.xy(a, b) for a, b in path]
            outlet, cut = "حد منطقة الكنتور", len(pts)
            for n_, (x, y) in enumerate(pts):
                if n_ * g.cell < 10:
                    continue
                if wadis and _nearest_dist(wadis, x, y) < g.cell:
                    outlet, cut = "وادٍ", n_ + 1
                    break
                if streets and _nearest_dist(streets, x, y) < g.cell and _nearest_dist([P], x, y) > width:
                    outlet, cut = "شارع", n_ + 1
                    break
            pts = [(p["x"], p["y"])] + pts[1:cut]
            L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
            z_end = terrain.elevation(*pts[-1]) if pts else None
            slope = (p[key] - z_end) / L if (z_end is not None and L > 0) else 0.0
            ch = size_channel(q, slope, o["manning_n"], o["freeboard"], o["max_velocity"])
            sags.append({"road": r_i, "s": round(p["s"], 1), "x": round(p["x"], 2), "y": round(p["y"], 2),
                         "z": round(p[key], 2), "area": round(area, 0), "road_len": round(road_len, 1),
                         "q": round(q, 3), "outlet": outlet, "lane_len": round(L, 1), "slope": round(slope, 4),
                         "channel": ch, "path": [[round(x, 2), round(y, 2)] for x, y in pts]})

    # --- الأودية المقترحة (شبكة الجريان فوق حد المساحة)
    thr = o["stream_ha"] * 10000
    is_stream = [[acc[j][i] >= thr for i in range(g.nx)] for j in range(g.ny)]
    upstream = [[0] * g.nx for _ in range(g.ny)]
    for j in range(g.ny):
        for i in range(g.nx):
            d = down[j][i]
            if is_stream[j][i] and d:
                upstream[d[1]][d[0]] += 1
    wadis_out = []
    used = set()
    heads = [(i, j) for j in range(g.ny) for i in range(g.nx) if is_stream[j][i] and upstream[j][i] == 0]
    heads.sort(key=lambda c: -filled[c[1]][c[0]])
    for hi, hj in heads:
        cells = []
        i, j = hi, hj
        while (i, j) not in used:
            cells.append((i, j))
            used.add((i, j))
            d = down[j][i]
            if d is None:
                break
            i, j = d
        if (i, j) in used and cells and cells[-1] != (i, j):
            cells.append((i, j))   # نصل الفرع بالمجرى الذي يصب فيه
        if len(cells) < 3:
            continue
        pts = [g.xy(a, b) for a, b in cells]
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        if L < 3 * g.cell:
            continue
        z_top, z_bot = filled[cells[0][1]][cells[0][0]], filled[cells[-1][1]][cells[-1][0]]
        area = acc[cells[-1][1]][cells[-1][0]]
        slope = max((z_top - z_bot) / L, 0.003)
        q = peak_flow(area, o["runoff_c"], o["intensity"])
        wadis_out.append({"path": [[round(x, 2), round(y, 2)] for x, y in pts], "length": round(L, 1),
                          "area": round(area, 0), "q": round(q, 3), "slope": round(slope, 4),
                          "channel": size_channel(q, slope, o["manning_n"], o["freeboard"], o["max_velocity"])})
    wadis_out.sort(key=lambda w: -w["area"])
    return {"sags": sags, "wadis": wadis_out, "cell": round(g.cell, 1), "params": o}
