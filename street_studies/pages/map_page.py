"""صفحة «المخطط والمسارات»: تحديد القطعة ورسم الشارع والجدران والبنود، وربط الكميات بالنموذج."""
import math

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from .. import geo
from ..data import format_num
from ..map_canvas import MapCanvas
from ..theme import C, S1, S2, S3, S4
from ..widgets import NumberEdit, button, divider, label, repolish

DTYPES = [("road", "شارع", "طول الشارع"), ("line", "خط", "م.ط"), ("point", "نقاط", "عدد"),
          ("area", "مساحة", "م²"), ("volume", "حجم", "م³"), ("wallR", "دبش", "جدار"), ("wallC", "مسلح", "جدار")]
UNIT_OF = {"line": "م.ط", "point": "عدد", "area": "م²", "volume": "م³"}
# بنود لا تُرسم (تُحسب تلقائياً أو دهانات)
NOT_DRAWN = {"RD-001", "RD-008", "RD-009", "RD-005", "RD-006"}
SHARE_MODES = [
    ("once", "مرة واحدة للأسبق — الأول كامل، واللاحق بدون المشترك"),
    ("exclusive", "غير المشترك فقط — كل مواطن بدون الجزء المشترك"),
    ("split", "تقسيم بالتساوي بين المشتركين"),
    ("full", "احتساب كامل لكل مواطن (تكرار)"),
]
COLORS = {"road": "#E8590C", "wallR": "#6D4C41", "wallC": "#546E7A", "line": "#1565C0",
          "point": "#C62828", "area": "#2E7D32", "volume": "#8E24AA", "other": "#6F42C1"}


def _rel(P, ox, oy):
    return [(q[0] - ox, q[1] - oy) for q in P]


def _abs(P, ox, oy):
    return [[round(q[0] + ox, 3), round(q[1] + oy, 3)] for q in P]


def share_info(lines, w, kind, code, others, own_name=""):
    """طول الخطوط والجزء المشترك مع مسارات مواطنين آخرين (عينات كل ~2م).
    others: [(name, [خطوط نسبية], عرض)]. يرجع len, shared, bill(مقسّم), with."""
    total = shared = split_bill = 0.0
    who = {}
    own = max((w or 1) / 2, 1.5)
    for li, P in enumerate(lines):
        for i in range(1, len(P)):
            a, b = P[i - 1], P[i]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L <= 0:
                continue
            k = max(1, round(L / 2))
            sl = L / k
            for q in range(k):
                t = (q + .5) / k
                x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
                # تكرار داخل خطوط نفس المواطن
                if any(geo.dist_seg(x, y, Q[j - 1], Q[j]) <= own for Q in lines[:li] for j in range(1, len(Q))):
                    continue
                hits = []
                for name, olines, ow in others:
                    tol = max(w or 1, ow if kind == "road" else (w or 1)) / 2 + 2
                    if any(geo.dist_seg(x, y, Q[j - 1], Q[j]) <= tol for Q in olines for j in range(1, len(Q))):
                        hits.append(name)
                total += sl
                if hits:
                    shared += sl
                    for nm in hits:
                        who[nm] = who.get(nm, 0) + sl
                split_bill += sl / (1 + len(hits))
    return {"len": total, "shared": shared, "split": split_bill,
            "with": [{"n": n, "l": round(v, 1)} for n, v in who.items()]}


def billed(info, mode):
    if mode == "full":
        return round(info["len"], 2)
    if mode == "split":
        return round(info["split"], 2)
    return round(max(0.0, info["len"] - info["shared"]), 2)


def lines_of_kind(path, kind, code=None):
    if not path:
        return []
    if kind == "road":
        return path.get("roads") or []
    if kind in ("wallR", "wallC"):
        return path.get("walls" + kind[-1]) or []
    g = (path.get("items") or {}).get(code) or {}
    return g.get("lines") or []


class MapPage(QWidget):
    back_requested = Signal()
    path_saved = Signal(dict)

    def __init__(self, store, settings, entry, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.store, self.settings, self.entry = store, settings, entry
        self.geo = None
        self.canvas = None
        self.terrain = None
        self.profile_result = None
        self.sewer_result = None
        self.drain_result = None
        self._contours_rel = []
        self.reset_session()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._panel())
        self.map_holder = QVBoxLayout()
        self.loading = label("جارٍ تحميل المخطط التنظيمي…", "pageSub")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.map_holder.addWidget(self.loading)
        holder = QWidget()
        holder.setLayout(self.map_holder)
        root.addWidget(holder, 1)

    # ---------- الحالة
    # ---------- الكنتور والبروفايل
    def pick_contours(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف الكنتور", "", "DXF (*.dxf)")
        if not path:
            return
        from PySide6.QtWidgets import QApplication
        from .. import terrain
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            terrain.load_dxf(path)   # تحقق قبل الإرفاق
            att = self.store.add_attachment(path)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self.window(), "تعذّر قراءة الكنتور", str(e))
            return
        QApplication.restoreOverrideCursor()
        self.set_contours(att)

    def set_contours(self, att):
        self.entry.contours = att
        if att is None:
            self.entry.contour_interval = None
        self.profile_result = None
        self.load_terrain()

    def load_terrain(self):
        """تحميل نموذج الأرض من كنتور المعاملة الحالية."""
        from .. import terrain
        att = getattr(self.entry, "contours", None)
        self.terrain = None
        if att:
            try:
                self.terrain = terrain.load_dxf(self.store.attachment_path(att),
                                                getattr(self.entry, "contour_interval", None))
            except Exception as e:  # noqa: BLE001
                self.contour_info.setText(f"تعذّر قراءة الكنتور: {e}")
        T = self.terrain
        self.contour_rm.setVisible(bool(att))
        if T:
            self.contour_info.setText(f"{att['name']} — المناسيب {T.zmin:g} إلى {T.zmax:g} م · "
                                      f"{len(T.contours)} خط · الفاصل المكتشف {T.detected_interval or '—'} م")
            self.interval.set_value(T.interval)
            ox, oy = (self.geo.ox, self.geo.oy) if self.geo else (0, 0)
            self._contours_rel = [(z, [(x - ox, y - oy) for x, y in P]) for z, P in T.contours]
        elif not att:
            self.contour_info.setText("لا يوجد كنتور مرفق لهذه المعاملة.")
            self.interval.setText("")
            self._contours_rel = []
        self.profile_btn.setEnabled(bool(T))
        self.sewer_btn.setEnabled(bool(T))
        self.drain_btn.setEnabled(bool(T))
        self._update_profile_info()
        self._update_sewer_info()
        self._update_drain_info()
        if self.canvas:
            self.canvas.update()

    def _interval_changed(self):
        v = self.interval.value()
        if self.terrain and v > 0:
            self.terrain.interval = v
            self.entry.contour_interval = v
            self.canvas.update()

    def open_profile(self):
        if not self.terrain:
            self._say("أرفق ملف الكنتور أولاً.", True)
            return
        self.commit_current()
        if not self.roads:
            self._say("ارسم مسار الشارع أولاً (نوع الرسم: شارع).", True)
            return
        from ..profile_view import ProfileDialog
        ox, oy = self.geo.ox, self.geo.oy
        roads = [[(x + ox, y + oy) for x, y in P] for P in self.roads]
        params = (self.profile_result or {}).get("params") or self.settings.get("profile_params") or {}
        dlg = ProfileDialog(roads, self.w.value() or 6, self.terrain, params, self.window())
        dlg.apply_requested.connect(self._apply_profile)
        dlg.exec()

    def _apply_profile(self, result):
        self.profile_result = dict(result, params=dict(result["roads"][0]["params"]) if result["roads"] else {})
        self.settings["profile_params"] = {k: v for k, v in self.profile_result["params"].items() if k != "width"}
        self.settings.save()
        self._update_profile_info()
        self.canvas.update()
        self._say(f"تم حساب البروفايل: حفر {result['cut']:.1f} م³ · ردم {result['fill']:.1f} م³ — "
                  "اضغط «حفظ وربط الكميات بالنموذج» لنقلها.")

    def _update_profile_info(self):
        r = getattr(self, "profile_result", None)
        if not r:
            self.profile_info.setText("")
            return
        bad = sum(d["design_over"] + d["cf_over"] for d in r["roads"])
        self.profile_info.setText(f"البروفايل: حفر {r['cut']:.1f} م³ · ردم {r['fill']:.1f} م³"
                                  + (f" · ⚠ {bad} مخالفة" if bad else " · يحقق الشرطين ✓"))

    def _profile_for_save(self):
        r = getattr(self, "profile_result", None)
        if not r:
            return None
        return r

    # ---------- الصرف الصحي
    def _outlets(self, roads_abs, radius):
        """مصارف محتملة لدخلات الخدمات: الشوارع المرسومة، والشوارع التنظيمية والأودية القريبة."""
        out = [("road", P, "الشارع المرسوم") for P in roads_abs]
        xs = [q[0] for P in roads_abs for q in P]
        ys = [q[1] for P in roads_abs for q in P]
        ox, oy = self.geo.ox, self.geo.oy
        from PySide6.QtCore import QRectF
        box = QRectF(min(xs) - ox - radius - 50, min(ys) - oy - radius - 50,
                     max(xs) - min(xs) + 2 * radius + 100, max(ys) - min(ys) + 2 * radius + 100)
        for ds in self.geo.datasets:
            for i, r in enumerate(ds.bbox):
                if ds.layers[i] in (geo.LAYER_ROAD, geo.LAYER_WADI) and r.intersects(box):
                    kind = "road" if ds.layers[i] == geo.LAYER_ROAD else "wadi"
                    out.append((kind, ds.abs_points(i), "شارع تنظيمي" if kind == "road" else "وادٍ"))
        return out

    def open_sewer(self):
        if not self.terrain:
            self._say("أرفق ملف الكنتور أولاً.", True)
            return
        self.commit_current()
        if not self.roads:
            self._say("ارسم مسار الشارع أولاً (نوع الرسم: شارع).", True)
            return
        from .. import sewer
        from ..sewer_view import SewerDialog
        ox, oy = self.geo.ox, self.geo.oy
        roads = [[(x + ox, y + oy) for x, y in P] for P in self.roads]
        w = self.w.value() or 6
        lots = sewer.frontage_lots(roads, w, self.geo.datasets, ox, oy)
        prof = self.profile_result

        def run(params):
            return sewer.analyze(roads, w, self.terrain, lots, prof, self._outlets(roads, params["search_radius"]),
                                 **params)
        if not prof:
            self._say("لم يُحسب البروفايل بعد — يُستخدم منسوب الأرض لمحور الشارع بدل المنسوب التصميمي.", True)
        dlg = SewerDialog(run, self.settings.get("sewer_params"), self.window())
        dlg.apply_requested.connect(self._apply_sewer)
        dlg.exec()

    def _apply_sewer(self, res):
        self.sewer_result = res
        self.settings["sewer_params"] = {k: v for k, v in res["params"].items()}
        self.settings.save()
        self._update_sewer_info()
        self.canvas.update()
        self._say("تم اعتماد فحص الصرف الصحي — اضغط «حفظ وربط الكميات بالنموذج» لحفظه مع السجل.")

    def _update_sewer_info(self):
        from .. import sewer
        r = getattr(self, "sewer_result", None)
        if not r:
            self.sewer_info.setText("")
            return
        c = r["counts"]
        lanes = [x["lane"] for x in r["lots"] if x.get("lane")]
        txt = f"الصرف: مخدومة {c[sewer.SERVED]} · بتعميق {c[sewer.DEEPEN]} · دخلات {c[sewer.LANE]}"
        if lanes:
            txt += f" (مجموع أطوال الدخلات {sum(x['length'] for x in lanes):.0f} م)"
        if c[sewer.NO_OUTLET]:
            txt += f" · بلا مصرف {c[sewer.NO_OUTLET]}"
        self.sewer_info.setText(txt)

    def _draw_sewer(self, p, cv):
        r = getattr(self, "sewer_result", None)
        if not r:
            return
        from ..sewer_view import STATUS_COLOR
        ox, oy = self.geo.ox, self.geo.oy
        for lot in r["lots"]:
            col = QColor(STATUS_COLOR[lot["status"]])
            fill = QColor(col)
            fill.setAlpha(45)
            P = [(x - ox, y - oy) for x, y in lot["poly"]]
            cv.stroke(p, P + P[:1], col, px=2, close=True, fill=fill)
            if lot.get("low"):
                q = cv.to_screen(lot["low"][0] - ox, lot["low"][1] - oy)
                p.setPen(QPen(QColor("#FFFFFF"), 1.2))
                p.setBrush(col)
                p.drawEllipse(q, 4, 4)
            ln = lot.get("lane")
            if ln:
                L = [(x - ox, y - oy) for x, y in ln["path"]]
                cv.stroke(p, L, "#8E24AA", width_m=ln["width"], px=2, dash=True)
                cv.label_at(p, L, f"دخلة خدمات {ln['width']:g} م — {ln['length']:.0f} م", "#8E24AA")

    # ---------- تجمع الأمطار والأودية
    def open_drainage(self):
        if not self.terrain:
            self._say("أرفق ملف الكنتور أولاً.", True)
            return
        self.commit_current()
        if not self.roads:
            self._say("ارسم مسار الشارع أولاً (نوع الرسم: شارع).", True)
            return
        from .. import drainage
        from ..drainage_view import DrainageDialog
        ox, oy = self.geo.ox, self.geo.oy
        roads = [[(x + ox, y + oy) for x, y in P] for P in self.roads]
        w = self.w.value() or 6

        def run(params):
            outs = self._outlets(roads, params["margin"])
            wadis = [P for k, P, _ in outs if k == "wadi"]
            streets = [P for k, P, n in outs if k == "road" and n != "الشارع المرسوم"]
            return drainage.analyze(roads, w, self.terrain, self.profile_result, wadis, streets, **params)
        dlg = DrainageDialog(run, self.settings.get("drain_params"), self.window())
        dlg.apply_requested.connect(self._apply_drainage)
        dlg.exec()

    def _apply_drainage(self, res):
        self.drain_result = res
        self.settings["drain_params"] = dict(res["params"])
        self.settings.save()
        self._update_drain_info()
        self.canvas.update()
        self._say("تم اعتماد دراسة تجمع الأمطار والأودية — اضغط «حفظ وربط الكميات بالنموذج» لحفظها مع السجل.")

    def _update_drain_info(self):
        r = getattr(self, "drain_result", None)
        if not r:
            self.drain_info.setText("")
            return
        lanes = sum(s["lane_len"] for s in r["sags"])
        self.drain_info.setText(f"الأمطار: {len(r['sags'])} نقطة تجمع (دخلات تصريف {lanes:.0f} م) · "
                                f"{len(r['wadis'])} وادٍ مقترح ({sum(w['length'] for w in r['wadis']):.0f} م)")

    def _draw_drainage(self, p, cv):
        r = getattr(self, "drain_result", None)
        if not r:
            return
        ox, oy = self.geo.ox, self.geo.oy
        for wd in r["wadis"]:
            P = _rel(wd["path"], ox, oy)
            c = wd["channel"]
            cv.stroke(p, P, "#0277BD", width_m=max(c["width"], 1.0), px=2.5)
            cv.label_at(p, P, f"وادٍ مقترح {c['width']:g}×{c['depth']:g} م · Q={wd['q']:.2f}", "#01579B")
        for n, sg in enumerate(r["sags"], 1):
            P = _rel(sg["path"], ox, oy)
            cv.stroke(p, P, "#00ACC1", px=2.5, dash=True)
            q = cv.to_screen(sg["x"] - ox, sg["y"] - oy)
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))
            p.setBrush(QColor("#0288D1"))
            p.drawEllipse(q, 7, 7)
            cv.label_at(p, P[:2] if len(P) > 1 else P, f"تجمع أمطار {n} → {sg['outlet']} ({sg['lane_len']:.0f} م)",
                        "#00838F")

    def _draw_terrain(self, p, cv):
        self._draw_drainage(p, cv)
        self._draw_sewer(p, cv)
        if getattr(self, "terrain", None) and self.show_contours.isChecked():
            T = self.terrain
            step = T.interval or 10
            for z, P in self._contours_rel:
                major = abs((z / (step * 5)) - round(z / (step * 5))) < 1e-6
                cv.stroke(p, P, "#8D6E63", px=1.8 if major else 0.9, alpha=200 if major else 140)
                if (major and cv.s > 0.6) or cv.s > 2.5:
                    cv.label_at(p, P[len(P) // 2:len(P) // 2 + 2], f"{z:g}", "#6D4C41")
        # المقاطع التي يتجاوز ميل أرضها الحد (من آخر بروفايل)
        r = getattr(self, "profile_result", None)
        if r:
            ox, oy = self.geo.ox, self.geo.oy
            for d in r["roads"]:
                g = d["params"]["max_grade"]
                st = d["stations"]
                for a, b in zip(st, st[1:]):
                    ds = b["s"] - a["s"]
                    if ds > 0 and abs(b["zc"] - a["zc"]) / ds > g + 0.005:
                        cv.stroke(p, [(a["x"] - ox, a["y"] - oy), (b["x"] - ox, b["y"] - oy)], "#D32F2F", px=5)

    def reset_session(self):
        self.roads, self.wallsR, self.wallsC = [], [], []
        self.items = {}
        self.pts = []
        self.drawing = False
        self.sel = None
        self.history = []   # لتراجع الخطوط المكتملة: (النوع، المفتاح)

    def ensure_loaded(self):
        if self.geo is not None:
            return True
        try:
            self.geo = geo.GeoStore.get()
        except Exception as e:  # noqa: BLE001
            self.loading.setText(f"تعذّر تحميل بيانات المخطط: {e}")
            return False
        self.canvas = MapCanvas(self.geo)
        self.canvas.overlay = self._overlay
        self.canvas.extra_snap = lambda: self.roads + self.wallsR + self.wallsC + [
            P for g in self.items.values() for P in g["lines"] + g["polys"]] + ([self.pts] if self.pts else [])
        self.canvas.clicked.connect(self._on_click)
        self.canvas.finished.connect(self.commit_current)
        self.canvas.cancelled.connect(self.cancel_current)
        self.canvas.undo.connect(self.undo)
        self.canvas.moved.connect(self._on_move)
        self.canvas.offset = (float(self.settings.get("aerial_dx", 20)), float(self.settings.get("aerial_dy", 170)))
        self.loading.hide()
        self.map_holder.addWidget(self.canvas, 1)
        self.dx.set_value(self.canvas.offset[0])
        self.dy.set_value(self.canvas.offset[1])
        self._refresh_layers()
        return True

    # ---------- اللوحة الجانبية
    def _panel(self):
        outer = QFrame()
        outer.setObjectName("mapPanel")
        outer.setFixedWidth(360)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("scrollBody")
        scroll.setWidget(body)
        ol.addWidget(scroll)
        v = QVBoxLayout(body)
        v.setContentsMargins(S4, S4, S4, S4)
        v.setSpacing(S3)

        v.addWidget(label("المخطط والمسارات", "sectionTitle"))
        self.citizen = label("", "caption", wrap=True)
        v.addWidget(self.citizen)

        # البحث
        r = QHBoxLayout()
        r.setSpacing(S2)
        from PySide6.QtWidgets import QLineEdit
        self.query = QLineEdit()
        self.query.setPlaceholderText("رقم القطعة…")
        self.query.returnPressed.connect(self.search)
        b = button("بحث", "secondary", "mdi6.magnify")
        b.clicked.connect(self.search)
        r.addWidget(self.query, 1)
        r.addWidget(b)
        v.addLayout(r)
        self.hits = QListWidget()
        self.hits.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hits.setMaximumHeight(130)
        self.hits.hide()
        self.hits.itemClicked.connect(lambda it: self.select(*it.data(Qt.ItemDataRole.UserRole), zoom=True))
        v.addWidget(self.hits)
        self.info = label("انقر على قطعة لتحديدها.", "caption", wrap=True)
        v.addWidget(self.info)
        v.addWidget(divider())

        # الطبقات والصورة الجوية
        self.aer = QCheckBox("الصورة الجوية (تحتاج إنترنت أول مرة)")
        self.aer.toggled.connect(self._aerial_toggled)
        v.addWidget(self.aer)
        op = QHBoxLayout()
        op.addWidget(label("الشفافية", "caption"))
        self.op = QSlider(Qt.Orientation.Horizontal)
        self.op.setRange(20, 100)
        self.op.setValue(85)
        self.op.valueChanged.connect(self._opacity)
        op.addWidget(self.op, 1)
        v.addLayout(op)
        cal = QGridLayout()
        cal.setSpacing(S1)
        cal.addWidget(label("إزاحة الصورة X", "caption"), 0, 0)
        cal.addWidget(label("Y", "caption"), 0, 1)
        self.dx, self.dy = NumberEdit("20"), NumberEdit("170")
        for e in (self.dx, self.dy):
            e.setValidator(None)
            e.editingFinished.connect(self._offset_changed)
        cal.addWidget(self.dx, 1, 0)
        cal.addWidget(self.dy, 1, 1)
        v.addLayout(cal)
        arrows = QHBoxLayout()
        arrows.setSpacing(S1)
        self.step = 5
        for ic, tip, d in (("mdi6.arrow-left", "يسار", (-1, 0)), ("mdi6.arrow-right", "يمين", (1, 0)),
                           ("mdi6.arrow-up", "شمال", (0, 1)), ("mdi6.arrow-down", "جنوب", (0, -1))):
            ab = button("", "secondary", ic)
            ab.setToolTip(f"تحريك الصورة {tip}")
            ab.setProperty("compact", True)
            ab.clicked.connect(lambda _=False, d=d: self._shift(*d))
            arrows.addWidget(ab)
        self.step_btn = button("خطوة 5م", "secondary")
        self.step_btn.setProperty("compact", True)
        self.step_btn.clicked.connect(self._cycle_step)
        rs = button("", "ghost", "mdi6.restore")
        rs.setToolTip("إعادة الإزاحة الافتراضية (20، 170)")
        rs.clicked.connect(lambda: self._set_offset(20, 170))
        arrows.addWidget(self.step_btn)
        arrows.addWidget(rs)
        arrows.addStretch(1)
        v.addLayout(arrows)
        v.addWidget(label("حرّك الصورة الجوية حتى تطابق حدود القطع.", "caption", wrap=True))

        self.layer_box = QVBoxLayout()
        self.layer_box.setSpacing(2)
        v.addLayout(self.layer_box)
        imp = QHBoxLayout()
        bi = button("استيراد لوحة DXF", "secondary", "mdi6.layers-plus")
        bi.setToolTip("أضف لوحة أو منطقة جديدة من ملف DXF بإحداثيات JTM")
        bi.clicked.connect(self.import_layer)
        imp.addWidget(bi)
        imp.addStretch(1)
        v.addLayout(imp)
        v.addWidget(divider())

        # الكنتور (المناسيب)
        v.addWidget(label("الكنتور والمناسيب", "fieldLabel"))
        self.contour_info = label("لا يوجد كنتور مرفق لهذه المعاملة.", "caption", wrap=True)
        v.addWidget(self.contour_info)
        cr = QHBoxLayout()
        cr.setSpacing(S2)
        bc = button("إرفاق كنتور DXF", "secondary", "mdi6.terrain")
        bc.setToolTip("ملف كنتور مقصوص حول القطعة والشارع (خطوط ثلاثية الأبعاد بمناسيب Z)، بأي فاصل")
        bc.clicked.connect(self.pick_contours)
        self.contour_rm = button("", "ghost", "mdi6.close")
        self.contour_rm.setToolTip("إزالة الكنتور")
        self.contour_rm.clicked.connect(lambda: self.set_contours(None))
        cr.addWidget(bc)
        cr.addWidget(self.contour_rm)
        cr.addStretch(1)
        v.addLayout(cr)
        ir = QHBoxLayout()
        ir.addWidget(label("فاصل الكنتور (م)", "caption"))
        self.interval = NumberEdit("تلقائي")
        self.interval.setMaximumWidth(90)
        self.interval.editingFinished.connect(self._interval_changed)
        ir.addWidget(self.interval)
        self.show_contours = QCheckBox("إظهار")
        self.show_contours.setChecked(True)
        self.show_contours.toggled.connect(lambda _: self.canvas.update() if self.canvas else None)
        ir.addWidget(self.show_contours)
        ir.addStretch(1)
        v.addLayout(ir)
        self.profile_btn = button("البروفايل الطولي للشارع", None, "mdi6.chart-line")
        self.profile_btn.setToolTip("ميل كل مقطع، المنسوب التصميمي (ميل ≤ 19% وقطع/ردم ≤ 4 م على الواجهة)، والحفر والردم")
        self.profile_btn.clicked.connect(self.open_profile)
        v.addWidget(self.profile_btn)
        self.profile_info = label("", "caption", wrap=True)
        v.addWidget(self.profile_info)
        self.sewer_btn = button("فحص الصرف الصحي ودخلات الخدمات", "secondary", "mdi6.pipe")
        self.sewer_btn.setToolTip("هل كل قطعة على الشارع مخدومة بالصرف الصحي بالجاذبية؟ وإلا تُقترح دخلة خدمات")
        self.sewer_btn.clicked.connect(self.open_sewer)
        v.addWidget(self.sewer_btn)
        self.sewer_info = label("", "caption", wrap=True)
        v.addWidget(self.sewer_info)
        self.drain_btn = button("تجمع الأمطار والأودية", "secondary", "mdi6.weather-pouring")
        self.drain_btn.setToolTip("نقاط تجمع مياه الأمطار على الشارع ودخلات تصريفها، والأودية المقترحة من الكنتور")
        self.drain_btn.clicked.connect(self.open_drainage)
        v.addWidget(self.drain_btn)
        self.drain_info = label("", "caption", wrap=True)
        v.addWidget(self.drain_info)
        v.addWidget(divider())

        # إعدادات المسار
        g = QGridLayout()
        g.setSpacing(S2)
        g.addWidget(label("عرض الشارع (م)", "fieldLabel"), 0, 0)
        g.addWidget(label("محيط DXF حول القطعة (م)", "fieldLabel"), 0, 1)
        self.w = NumberEdit("6")
        self.w.set_value(6)
        self.w.textChanged.connect(self.update_totals)
        self.margin = NumberEdit("60")
        self.margin.set_value(60)
        g.addWidget(self.w, 1, 0)
        g.addWidget(self.margin, 1, 1)
        v.addLayout(g)
        v.addWidget(label("الجزء المشترك مع مواطنين آخرين", "fieldLabel"))
        self.mode = QComboBox()
        self.mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mode.setMinimumContentsLength(20)
        for k, t in SHARE_MODES:
            self.mode.addItem(t, k)
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.settings.get("share_mode") or "once")))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        v.addWidget(self.mode)
        self.share = label("", "caption", wrap=True)
        v.addWidget(self.share)
        v.addWidget(divider())

        # نوع الرسم
        v.addWidget(label("نوع الرسم", "fieldLabel"))
        grid = QGridLayout()
        grid.setSpacing(S1)
        self.dtype_btns = {}
        for n, (key, t, sub) in enumerate(DTYPES):
            bt = QPushButton(f"{t}\n{sub}")
            bt.setObjectName("dtype")
            bt.setCheckable(True)
            bt.setAutoExclusive(True)
            bt.setCursor(Qt.CursorShape.PointingHandCursor)
            bt.clicked.connect(lambda _=False, k=key: self.set_dtype(k))
            grid.addWidget(bt, n // 4, n % 4)
            self.dtype_btns[key] = bt
        self.dtype_btns["road"].setChecked(True)
        self.dtype = "road"
        v.addLayout(grid)
        self.item_wrap = QWidget()
        iw = QVBoxLayout(self.item_wrap)
        iw.setContentsMargins(0, 0, 0, 0)
        iw.setSpacing(2)
        iw.addWidget(label("البند المرتبط بالرسم", "caption"))
        self.item = QComboBox()
        self.item.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.item.setMinimumContentsLength(18)
        iw.addWidget(self.item)
        self.item_hint = label("", "caption", wrap=True)
        iw.addWidget(self.item_hint)
        dr = QHBoxLayout()
        dr.addWidget(label("السماكة / العمق (م)", "caption"))
        self.depth = NumberEdit("0.30")
        self.depth.setMaximumWidth(110)
        self.depth.editingFinished.connect(self._depth_changed)
        dr.addWidget(self.depth)
        dr.addStretch(1)
        self.depth_row = QWidget()
        self.depth_row.setLayout(dr)
        dr.setContentsMargins(0, 0, 0, 0)
        iw.addWidget(self.depth_row)
        self.item.currentIndexChanged.connect(self._item_changed)
        self.item_wrap.hide()
        v.addWidget(self.item_wrap)
        self.osnap = QCheckBox("التقاط تلقائي على الخطوط (OSNAP)")
        self.osnap.setChecked(True)
        self.osnap.toggled.connect(lambda on: setattr(self.canvas, "osnap", on) if self.canvas else None)
        v.addWidget(self.osnap)

        self.draw_btn = button("ابدأ الرسم", None, "mdi6.pencil")
        self.draw_btn.clicked.connect(self.toggle_draw)
        v.addWidget(self.draw_btn)
        r2 = QHBoxLayout()
        r2.setSpacing(S2)
        self.new_line = button("خط جديد", "secondary", "mdi6.plus")
        self.new_line.setToolTip("ثبّت الخط الحالي وابدأ خطاً آخر لنفس المواطن (أو الزر الأيمن)")
        self.new_line.clicked.connect(self.commit_current)
        self.undo_btn = button("تراجع", "secondary", "mdi6.undo")
        self.undo_btn.clicked.connect(self.undo)
        clear = button("مسح الرسم", "danger", "mdi6.eraser")
        clear.clicked.connect(self.clear_drawing)
        r2.addWidget(self.new_line)
        r2.addWidget(self.undo_btn)
        r2.addWidget(clear)
        v.addLayout(r2)
        self.totals = label("", "caption", wrap=True)
        self.totals.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.totals)
        self.msg = label("", "caption", wrap=True)
        v.addWidget(self.msg)
        v.addWidget(divider())
        self.save_btn = button("حفظ وربط الكميات بالنموذج", "success", "mdi6.link-variant")
        self.save_btn.clicked.connect(self.save)
        v.addWidget(self.save_btn)
        back = button("رجوع إلى النموذج", "secondary", "mdi6.arrow-right")
        back.clicked.connect(self.back_requested.emit)
        v.addWidget(back)
        v.addStretch(1)
        self.coord = label("", "muted")
        self.coord.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        v.addWidget(self.coord)
        return outer

    def _refresh_layers(self):
        while self.layer_box.count():
            it = self.layer_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for key, t in ((geo.LAYER_PARCEL, "القطع (أصفر)"), (geo.LAYER_ROAD, "الشوارع التنظيمية (أحمر)"),
                       (geo.LAYER_WADI, "الأودية ومجاري المياه (أزرق)")):
            cb = QCheckBox(t)
            cb.setChecked(self.canvas.layers_on.get(key, True))
            cb.toggled.connect(lambda on, k=key: self._layer(k, on))
            self.layer_box.addWidget(cb)
        for ds in self.geo.datasets[1:]:
            row = QHBoxLayout()
            w = QWidget()
            w.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(label(f"لوحة مستوردة: {ds.name}", "caption"), 1)
            rm = button("", "ghost", "mdi6.close")
            rm.setToolTip("إزالة اللوحة المستوردة")
            rm.clicked.connect(lambda _=False, d=ds: self._remove_layer(d))
            row.addWidget(rm)
            self.layer_box.addWidget(w)

    def refresh(self):
        """عند الانتقال للصفحة من الشريط الجانبي: نعيد التحميل فقط إن تغيّر سجل المواطن في النموذج."""
        key = (self.entry.edit_index, id(self.entry.map_path), self.entry.name.text())
        if getattr(self, "_ctx", None) != key or self.canvas is None:
            QTimer.singleShot(0, self.open_for_form)

    # ---------- فتح الصفحة لمواطن
    def open_for_form(self):
        """تُستدعى عند فتح الصفحة: تحميل رسم المواطن الحالي من النموذج وتحديد قطعته."""
        if not self.ensure_loaded():
            return
        self.reset_session()
        e = self.entry
        self._ctx = (e.edit_index, id(e.map_path), e.name.text())
        self.profile_result = (e.map_path or {}).get("profile")
        self.sewer_result = (e.map_path or {}).get("sewer")
        self.drain_result = (e.map_path or {}).get("drainage")
        self.load_terrain()
        name = e.name.text().strip() or "مواطن جديد"
        plan = e.plan_card.values() or {}
        self.citizen.setText(f"المواطن: <b>{name}</b>" + (f" · قطعة {e.piece.text()}" if e.piece.text() else "")
                             + (f" · حوض {plan.get('basin')}" if plan.get("basin") else ""))
        ox, oy = self.geo.ox, self.geo.oy
        path = e.map_path
        if path:
            self.roads = [_rel(P, ox, oy) for P in path.get("roads") or []]
            self.wallsR = [_rel(P, ox, oy) for P in path.get("wallsR") or []]
            self.wallsC = [_rel(P, ox, oy) for P in path.get("wallsC") or []]
            for c, g in (path.get("items") or {}).items():
                self.items[c] = {"unit": g.get("unit"), "lines": [_rel(P, ox, oy) for P in g.get("lines") or []],
                                 "points": _rel(g.get("points") or [], ox, oy),
                                 "polys": [_rel(P, ox, oy) for P in g.get("polys") or []]}
            if path.get("w"):
                self.w.set_value(path["w"])
            if path.get("margin") is not None:
                self.margin.set_value(path["margin"])
        self.set_dtype("road")
        self.query.setText(e.piece.text())
        self.canvas.selected = None
        found = False
        if path and path.get("parcelPts"):
            found = self._select_by_points(path["parcelPts"])
        if not found and e.piece.text().strip():
            self.search()
        elif not found and path:
            self._fit_drawing()
        self.update_totals()
        self.canvas.update()

    def _select_by_points(self, pts):
        """إعادة تحديد القطعة المحفوظة من مركز مضلعها."""
        cx = sum(p[0] for p in pts) / len(pts) - self.geo.ox
        cy = sum(p[1] for p in pts) / len(pts) - self.geo.oy
        ds, i = self.geo.pick(cx, cy)
        if ds is None:
            return False
        self.select(ds, i, zoom=True)
        return True

    def _fit_drawing(self):
        allp = [q for P in self.roads + self.wallsR + self.wallsC for q in P]
        if allp:
            from PySide6.QtCore import QRectF
            xs, ys = [p[0] for p in allp], [p[1] for p in allp]
            self.canvas.fit(QRectF(min(xs) - 40, min(ys) - 40, max(xs) - min(xs) + 80, max(ys) - min(ys) + 80))

    # ---------- البحث والتحديد
    def search(self):
        if not self.ensure_loaded():
            return
        q = self.query.text().strip()
        plan = self.entry.plan_card.values() or {}
        try:
            target = float(plan.get("parcelArea") or 0) or None
        except ValueError:
            target = None
        ranked = self.geo.find(q, target)
        self.hits.clear()
        if not ranked:
            self.hits.hide()
            self._say(f"لا توجد قطعة مطابقة لـ «{q}».", True)
            return
        for n, r in enumerate(ranked[:15]):
            ds, i = r["ds"], r["i"]
            txt = f"({n + 1}/{len(ranked)}) قطعة {ds.nums[i] or '—'} · ≈ {round(r['area'])} م²"
            if r["rel"] is not None:
                txt += f" · فرق {r['rel'] * 100:.1f}%"
            it = QListWidgetItem(txt)
            it.setData(Qt.ItemDataRole.UserRole, (ds, i))
            self.hits.addItem(it)
        self.hits.setVisible(len(ranked) > 1)
        self.canvas.candidates = [(r["ds"], r["i"]) for r in ranked[:15]]
        best = ranked[0]
        self.select(best["ds"], best["i"], zoom=True)
        if len(ranked) > 1:
            self._say(f"وُجد {len(ranked)} قطعة بنفس الرقم (في أحواض مختلفة)"
                      + (" — رُتّبت حسب قرب المساحة من مخطط الموقع" if target else
                         " — اختر من القائمة، أو أرفق مخطط الموقع لترتيبها بالمساحة") + ".", True)

    def select(self, ds, i, zoom=False):
        self.sel = (ds, i)
        self.canvas.selected = self.sel
        plan = self.entry.plan_card.values() or {}
        info = f"القطعة: <b>{ds.nums[i] or 'بدون رقم'}</b> — المساحة ≈ {round(ds.area(i))} م²"
        try:
            pa = float(plan.get("parcelArea") or 0)
        except ValueError:
            pa = 0
        if pa:
            info += f" (مخطط الموقع: {pa:g} م²)"
        self.info.setText(info)
        if zoom:
            self.canvas.fit_parcel(ds, i)
        self.canvas.update()

    def _on_click(self, x, y, _btn):
        if self.drawing:
            self.add_point(x, y)
            return
        ds, i = self.geo.pick(x, y)
        if ds is not None:
            self.canvas.candidates = []
            self.hits.hide()
            self.select(ds, i)

    def _on_move(self, x, y):
        self.coord.setText(f"E {x + self.geo.ox:,.2f}   N {y + self.geo.oy:,.2f}")

    # ---------- الرسم
    def set_dtype(self, key):
        if self.drawing and self.pts:
            self.commit_current()
        self.dtype = key
        self.dtype_btns[key].setChecked(True)
        unit = UNIT_OF.get(key)
        self.item_wrap.setVisible(bool(unit))
        if unit:
            cur = self.item.currentData()
            self.item.clear()
            for it in self.store.items:
                if it["unit"] == unit and it["code"] not in NOT_DRAWN:
                    self.item.addItem(f"{it['code']} — {it['name']}", it["code"])
            i = self.item.findData(cur)
            self.item.setCurrentIndex(max(0, i))
            self.item_hint.setText({"line": "ارسم خطاً — الكمية = الطول بالمتر الطولي.",
                                    "point": "كل نقرة = نقطة واحدة في الكمية.",
                                    "area": "ارسم مضلعاً — الزر الأيمن يغلقه ويحسب م².",
                                    "volume": "ارسم مضلعاً — الكمية = المساحة × السماكة/العمق (م³)."}[key])
        self.depth_row.setVisible(key == "volume")
        self._item_changed()
        if self.drawing:
            self._say(self._hint())
        self.update_totals()

    def _item_changed(self):
        if self.dtype == "volume":
            it = self.store.item(self.item.currentData() or "")
            self.depth.set_value((it or {}).get("depth") or 0.3)

    def _depth_changed(self):
        it = self.store.item(self.item.currentData() or "")
        if it is not None and self.depth.value() > 0:
            it["depth"] = self.depth.value()
            self.store.save()
            self.update_totals()

    def _hint(self):
        return {"road": "ارسم مسار الشارع: انقر لإضافة نقاط، الزر الأيمن أو نقر مزدوج لتثبيت الخط.",
                "volume": "حجم م³: انقر رؤوس المضلع، الزر الأيمن يُغلقه (الكمية = المساحة × السماكة).",
                "line": "خط م.ط: انقر النقاط، الزر الأيمن للتثبيت.",
                "point": "انقر لإضافة نقاط (كل نقطة = 1).",
                "area": "مضلع: انقر الرؤوس، الزر الأيمن يُغلق المضلع.",
                "wallR": "جدار دبش وباطون: انقر النقاط، الزر الأيمن للتثبيت.",
                "wallC": "جدار مسلح: انقر النقاط، الزر الأيمن للتثبيت."}[self.dtype] + \
            "  Esc إلغاء الخط الحالي · Backspace تراجع."

    def toggle_draw(self):
        if not self.ensure_loaded():
            return
        if self.drawing:
            self.commit_current()
            self.drawing = False
        else:
            if self.sel is None:
                self._say("حدّد القطعة أولاً (ابحث برقمها أو انقر عليها).", True)
                return
            self.drawing = True
            self._say(self._hint())
        self.canvas.drawing = self.drawing
        self.canvas.setCursor(Qt.CursorShape.CrossCursor if self.drawing else Qt.CursorShape.ArrowCursor)
        self.draw_btn.setText("إيقاف الرسم" if self.drawing else "ابدأ الرسم")
        self.draw_btn.setObjectName("secondary" if self.drawing else "")
        repolish(self.draw_btn)
        self.canvas.update()

    def _item_geom(self):
        code = self.item.currentData()
        if not code:
            return None
        return self.items.setdefault(code, {"unit": UNIT_OF[self.dtype], "lines": [], "points": [], "polys": []})

    def add_point(self, x, y):
        if self.dtype == "point":
            g = self._item_geom()
            if g is None:
                self._say("اختر بنداً بوحدة «عدد» أولاً.", True)
                return
            g["points"].append((x, y))
            self.history.append(("point", self.item.currentData()))
            self._say(f"نقطة #{len(g['points'])} — {self.item.currentText()}")
        else:
            if self.dtype in ("line", "area", "volume") and not self.item.currentData():
                self._say("اختر البند المرتبط أولاً.", True)
                return
            self.pts.append((x, y))
            if len(self.pts) > 1:
                if self.dtype in ("area", "volume"):
                    self._say(f"مضلع: {len(self.pts)} رؤوس · ≈ {geo.poly_area(self.pts):.1f} م²")
                else:
                    self._say(f"{len(self.pts)} نقاط · الطول ≈ {geo.length(self.pts):.2f} م")
        self.update_totals()
        self.canvas.update()

    def commit_current(self):
        P = self.pts
        self.pts = []
        if self.dtype == "road" and len(P) > 1:
            self.roads.append(P)
            self.history.append(("road", None))
        elif self.dtype in ("wallR", "wallC") and len(P) > 1:
            getattr(self, "walls" + self.dtype[-1]).append(P)
            self.history.append((self.dtype, None))
        elif self.dtype == "line" and len(P) > 1 and self._item_geom() is not None:
            self._item_geom()["lines"].append(P)
            self.history.append(("line", self.item.currentData()))
        elif self.dtype in ("area", "volume") and len(P) > 2 and self._item_geom() is not None:
            self._item_geom()["polys"].append(P)
            self.history.append(("area", self.item.currentData()))
        self.update_totals()
        self.canvas.update()

    def cancel_current(self):
        self.pts = []
        self.update_totals()
        self.canvas.update()

    def undo(self):
        if self.pts:
            self.pts.pop()
        elif self.history:
            kind, code = self.history.pop()
            if kind == "road" and self.roads:
                self.roads.pop()
            elif kind in ("wallR", "wallC") and getattr(self, "walls" + kind[-1]):
                getattr(self, "walls" + kind[-1]).pop()
            elif code in self.items:
                g = self.items[code]
                lst = {"line": g["lines"], "area": g["polys"], "point": g["points"]}[kind]
                if lst:
                    lst.pop()
        self.update_totals()
        self.canvas.update()

    def clear_drawing(self):
        if (self.roads or self.wallsR or self.wallsC or any(
                g["lines"] or g["points"] or g["polys"] for g in self.items.values())):
            if QMessageBox.question(self.window(), "مسح الرسم", "مسح كل الرسم الحالي لهذا المواطن؟") != \
                    QMessageBox.StandardButton.Yes:
                return
        self.reset_session_geometry()

    def reset_session_geometry(self):
        sel = self.sel
        self.reset_session()
        self.sel = sel
        self.drawing = False
        self.canvas.drawing = False
        self.draw_btn.setText("ابدأ الرسم")
        self.update_totals()
        self.canvas.update()

    # ---------- المشترك والكميات
    def _others(self, kind, code=None):
        """مسارات المواطنين الآخرين حسب وضع الاحتساب (مرة واحدة = السابقون فقط)."""
        mode = self.mode.currentData()
        idx = self.entry.edit_index
        out = []
        ox, oy = self.geo.ox, self.geo.oy
        for i, s in enumerate(self.store.streets):
            if i == idx or not s.get("path"):
                continue
            if mode == "once" and idx >= 0 and i > idx:
                continue
            lines = [_rel(P, ox, oy) for P in lines_of_kind(s["path"], kind, code)]
            if lines:
                out.append((s.get("name") or f"#{s.get('pieceNo', '')}", lines, s["path"].get("w") or 6))
        return out

    def compute(self):
        """أطوال/مساحات الرسم بعد تطبيق المشترك."""
        mode = self.mode.currentData()
        w = self.w.value() or 6
        res = {"reports": []}
        roads = self.roads + ([self.pts] if self.dtype == "road" and len(self.pts) > 1 else [])
        ir = share_info(roads, w, "road", None, self._others("road")) if roads else None
        res["road"] = billed(ir, mode) if ir else 0.0
        res["road_info"] = ir
        if ir and ir["shared"] > .5:
            res["reports"].append(f"شارع: مشترك ≈ {ir['shared']:.1f} م مع " +
                                  "، ".join(f"{x['n']} ({x['l']} م)" for x in ir["with"]) +
                                  f" ← المحتسب {res['road']:.1f} من {ir['len']:.1f} م")
        for kind in ("wallR", "wallC"):
            L = getattr(self, "walls" + kind[-1]) + ([self.pts] if self.dtype == kind and len(self.pts) > 1 else [])
            if L:
                ii = share_info(L, 0.4, kind, None, self._others(kind))
                res[kind] = billed(ii, mode)
                if ii["shared"] > .5:
                    res["reports"].append(f"{'جدار دبش' if kind == 'wallR' else 'جدار مسلح'}: مشترك ≈ "
                                          f"{ii['shared']:.1f} م ← المحتسب {res[kind]:.1f} م")
            else:
                res[kind] = 0.0
        res["items"] = {}
        for code, g in self.items.items():
            cur = self.item.currentData() if UNIT_OF.get(self.dtype) == g["unit"] else None
            if g["unit"] == "م.ط":
                L = g["lines"] + ([self.pts] if cur == code and self.dtype == "line" and len(self.pts) > 1 else [])
                if L:
                    ii = share_info(L, 0.5, "item", code, self._others("item", code))
                    res["items"][code] = billed(ii, mode)
                    if ii["shared"] > .5:
                        res["reports"].append(f"{code}: مشترك ≈ {ii['shared']:.1f} م ← المحتسب {res['items'][code]:.1f} م")
            elif g["unit"] == "عدد":
                if g["points"]:
                    res["items"][code] = float(len(g["points"]))
            else:
                A = sum(geo.poly_area(P) for P in g["polys"])
                if cur == code and self.dtype in ("area", "volume") and len(self.pts) > 2:
                    A += geo.poly_area(self.pts)
                if g["unit"] == "م³":
                    A *= float((self.store.item(code) or {}).get("depth") or 0.3)
                if A:
                    res["items"][code] = round(A, 2)
        return res

    def update_totals(self):
        if self.canvas is None:
            return
        r = self.compute()
        parts = []
        if r["road"]:
            n = len(self.roads) + (1 if self.dtype == "road" and len(self.pts) > 1 else 0)
            parts.append(f"<b style='color:{COLORS['road']}'>شارع: {r['road']:.2f} م</b> ({n} خط)")
        if r["wallR"] or r["wallC"]:
            parts.append(f"<b style='color:{COLORS['wallR']}'>جدران: دبش {r['wallR']:.1f} · مسلح {r['wallC']:.1f} م.ط</b>")
        for code, q in r["items"].items():
            it = self.store.item(code)
            parts.append(f"<b style='color:{COLORS['line']}'>{it['name'] if it else code}: {q:g} {it['unit'] if it else ''}</b>")
        self.totals.setText("<br>".join(parts))
        ir = r.get("road_info")
        if ir and ir["shared"] > .5:
            self.share.setText(f"⚠ جزء مشترك ≈ {ir['shared']:.1f} م مع: " +
                               "، ".join(f"{x['n']} ({x['l']} م)" for x in ir["with"]) +
                               f"<br>المحتسب لهذا المواطن: <b>{r['road']:.1f} م</b> من أصل {ir['len']:.1f} م")
            self.share.setStyleSheet(f"color:{C['danger']}")
        else:
            self.share.setText("لا يوجد جزء مشترك مع مسارات محفوظة." if ir else "")
            self.share.setStyleSheet("")
        self.share.setTextFormat(Qt.TextFormat.RichText)
        self.canvas.update()

    def _mode_changed(self):
        self.settings["share_mode"] = self.mode.currentData()
        self.settings.save()
        self.update_totals()

    # ---------- الحفظ والربط
    def save(self):
        if not self.ensure_loaded():
            return
        self.commit_current()
        has = self.roads or self.wallsR or self.wallsC or any(
            g["lines"] or g["points"] or g["polys"] for g in self.items.values())
        if not has:
            self._say("ارسم مساراً أو جداراً أو بنداً أولاً.", True)
            return
        if self.sel is None:
            self._say("حدّد القطعة أولاً.", True)
            return
        r = self.compute()
        mode = self.mode.currentData()
        if r["reports"]:
            msg = ("أجزاء مشتركة مع مواطنين آخرين:\n\n• " + "\n• ".join(r["reports"]) +
                   f"\n\nوضع الاحتساب: {dict(SHARE_MODES)[mode]}\n\nمتابعة بهذا الاحتساب؟")
            if QMessageBox.question(self.window(), "أجزاء مشتركة", msg) != QMessageBox.StandardButton.Yes:
                return
        ox, oy = self.geo.ox, self.geo.oy
        ds, i = self.sel
        parcel_pts = ds.abs_points(i)
        w = self.w.value() or 6
        # هل يلامس الشارع حدود القطعة؟ (تنبيه فقط)
        poly = [(x - ox, y - oy) for x, y in parcel_pts]
        near = not self.roads or any(
            min(geo.dist_seg(q[0], q[1], poly[k - 1], poly[k]) for k in range(1, len(poly))) <= 20
            for P in self.roads for q in (P[0], P[-1]))
        ir = r.get("road_info") or {"shared": 0, "with": []}
        path = {
            "roads": [_abs(P, ox, oy) for P in self.roads],
            "wallsR": [_abs(P, ox, oy) for P in self.wallsR],
            "wallsC": [_abs(P, ox, oy) for P in self.wallsC],
            "items": {c: {"unit": g["unit"], "lines": [_abs(P, ox, oy) for P in g["lines"]],
                          "points": _abs(g["points"], ox, oy), "polys": [_abs(P, ox, oy) for P in g["polys"]]}
                      for c, g in self.items.items() if g["lines"] or g["points"] or g["polys"]},
            "w": w, "len": r["road"], "bill": r["road"],
            "wallRLen": r["wallR"], "wallCLen": r["wallC"], "itemQty": r["items"],
            "parcel": ds.nums[i] or "", "parcelPts": [[round(x, 3), round(y, 3)] for x, y in parcel_pts],
            "parcelArea": round(ds.area(i), 2), "dataset": ds.name,
            "margin": max(self.margin.value(), 0), "shared": round(ir["shared"], 1), "with": ir["with"],
            "mode": mode, "out": not near,
            "profile": self._profile_for_save(),
            "sewer": getattr(self, "sewer_result", None),
            "drainage": getattr(self, "drain_result", None),
        }
        self.drawing = False
        self.canvas.drawing = False
        self.draw_btn.setText("ابدأ الرسم")
        self.path_saved.emit(path)

    # ---------- الطبقة العلوية
    def _overlay(self, p, cv):
        from PySide6.QtGui import QPainter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ox, oy = self.geo.ox, self.geo.oy
        # مسارات المواطنين الآخرين
        for idx, s in enumerate(self.store.streets):
            if idx == self.entry.edit_index or not s.get("path"):
                continue
            pth = s["path"]
            for P in pth.get("roads") or []:
                cv.stroke(p, _rel(P, ox, oy), COLORS["other"], width_m=pth.get("w") or 6, alpha=110)
            for k in ("wallsR", "wallsC"):
                for P in pth.get(k) or []:
                    cv.stroke(p, _rel(P, ox, oy), COLORS["other"], px=3, alpha=130, dash=True)
            first = (pth.get("roads") or [[]])[0]
            if first and cv.s > 1.2:
                cv.label_at(p, _rel(first, ox, oy), s.get("name", ""), COLORS["other"])
        w = self.w.value() or 6
        for P in self.roads:
            cv.stroke(p, P, COLORS["road"], width_m=w, px=2)
            cv.label_at(p, P, f"شارع {geo.length(P):.1f} م", COLORS["road"])
        for kind, name in (("wallR", "جدار دبش"), ("wallC", "جدار مسلح")):
            for P in getattr(self, "walls" + kind[-1]):
                cv.stroke(p, P, COLORS[kind], px=4, dash=kind == "wallR")
                cv.label_at(p, P, f"{name} {geo.length(P):.1f} م", COLORS[kind])
        for code, g in self.items.items():
            it = self.store.item(code)
            nm = it["name"] if it else code
            for P in g["lines"]:
                cv.stroke(p, P, COLORS["line"], px=3)
                cv.label_at(p, P, f"{nm} {geo.length(P):.1f} م", COLORS["line"])
            for P in g["polys"]:
                if g["unit"] == "م³":
                    dep = float((it or {}).get("depth") or 0.3)
                    cv.stroke(p, P, "#8E24AA", px=2, close=True, fill=QColor(142, 36, 170, 55))
                    cv.label_at(p, P, f"{nm} {geo.poly_area(P) * dep:.2f} م³", "#8E24AA")
                else:
                    cv.stroke(p, P, COLORS["area"], px=2, close=True, fill=QColor(46, 125, 50, 60))
                    cv.label_at(p, P, f"{nm} {geo.poly_area(P):.1f} م²", COLORS["area"])
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))
            p.setBrush(QColor(COLORS["point"]))
            for q in g["points"]:
                p.drawEllipse(cv.to_screen(*q), 5, 5)
            if g["points"]:
                cv.label_at(p, g["points"][:1], f"{nm} ×{len(g['points'])}", COLORS["point"])
        self._draw_terrain(p, cv)
        # الخط الجاري رسمه
        if self.pts:
            col = COLORS.get(self.dtype, COLORS["road"])
            Q = self.pts + ([cv.mouse] if cv.mouse and self.drawing else [])
            if self.dtype == "road":
                cv.stroke(p, Q, col, width_m=w, px=2, alpha=200)
            else:
                cv.stroke(p, Q, col, px=3, alpha=220, close=self.dtype in ("area", "volume"),
                          fill=QColor(46, 125, 50, 50) if self.dtype in ("area", "volume") else None)
            p.setPen(QPen(QColor("#FFFFFF"), 1.2))
            p.setBrush(QColor(col))
            for q in self.pts:
                p.drawEllipse(cv.to_screen(*q), 4, 4)
            if len(Q) > 1:
                val = (f"{geo.poly_area(Q):.1f} م²" if self.dtype in ("area", "volume") else f"{geo.length(Q):.2f} م")
                cv.label_at(p, Q, val, col)

    # ---------- الصورة الجوية والطبقات
    def _aerial_toggled(self, on):
        self.canvas.aerial = on
        self.canvas._invalidate()

    def _opacity(self, v):
        self.canvas.opacity = v / 100
        self.canvas.update()

    def _set_offset(self, dx, dy):
        self.dx.set_value(dx)
        self.dy.set_value(dy)
        self._offset_changed()

    def _offset_changed(self):
        dx, dy = self.dx.value(), self.dy.value()
        try:
            dx, dy = float(self.dx.text() or 0), float(self.dy.text() or 0)
        except ValueError:
            pass
        self.canvas.offset = (dx, dy)
        self.settings["aerial_dx"], self.settings["aerial_dy"] = dx, dy
        self.settings.save()
        self.canvas.update()

    def _shift(self, sx, sy):
        dx, dy = self.canvas.offset
        self._set_offset(dx + sx * self.step, dy + sy * self.step)

    def _cycle_step(self):
        self.step = {1: 5, 5: 10, 10: 50, 50: 1}[self.step]
        self.step_btn.setText(f"خطوة {self.step}م")

    def _layer(self, key, on):
        self.canvas.layers_on[key] = on
        self.canvas._invalidate()

    def import_layer(self):
        if not self.ensure_loaded():
            return
        path, _ = QFileDialog.getOpenFileName(self, "استيراد لوحة من DXF", "", "DXF (*.dxf)")
        if not path:
            return
        import os
        name, ok = QInputDialog.getText(self, "اسم اللوحة", "اسم اللوحة أو المنطقة:",
                                        text=os.path.splitext(os.path.basename(path))[0])
        if not ok:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            count, fn = geo.import_dxf(path, name or "لوحة", self.geo.ox, self.geo.oy)
            ds = self.geo.add_imported(fn)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self.window(), "تعذّر الاستيراد", str(e))
            return
        QApplication.restoreOverrideCursor()
        self._refresh_layers()
        self.canvas.fit(ds.extent)
        self._say(f"تم استيراد «{ds.name}» — {count} قطعة.")

    def _remove_layer(self, ds):
        if QMessageBox.question(self.window(), "إزالة لوحة", f"إزالة اللوحة المستوردة «{ds.name}»؟") == \
                QMessageBox.StandardButton.Yes:
            self.geo.remove_imported(ds)
            if self.sel and self.sel[0] is ds:
                self.sel = None
                self.canvas.selected = None
            self._refresh_layers()
            self.canvas._invalidate()

    def _say(self, text, warn=False):
        self.msg.setText(text)
        self.msg.setStyleSheet(f"color:{C['warning']}" if warn else "")


def render_path_image(path, store_streets=None, width=1600, height=1000):
    """صورة لمسار مواطن فوق المخطط (للتقرير). يرجع QImage أو None."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    try:
        g = geo.GeoStore.get()
    except Exception:  # noqa: BLE001
        return None
    ox, oy = g.ox, g.oy
    pts = [q for k in ("roads", "wallsR", "wallsC") for P in path.get(k) or [] for q in P]
    pts += [q for gg in (path.get("items") or {}).values() for P in (gg.get("lines") or []) + (gg.get("polys") or [])
            for q in P] + [q for gg in (path.get("items") or {}).values() for q in gg.get("points") or []]
    pts += path.get("parcelPts") or []
    for lot in (path.get("sewer") or {}).get("lots") or []:
        if lot.get("lane"):
            pts += lot["lane"]["path"]
    if not pts:
        return None
    xs, ys = [p[0] - ox for p in pts], [p[1] - oy for p in pts]
    m = max(path.get("margin") or 30, 20)
    cv = MapCanvas(g)
    cv.resize(width, height)
    cv.fit(QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m), 0.95)
    if path.get("parcelPts"):
        from PySide6.QtGui import QPolygonF
        sel_poly = QPolygonF([QPointF(x - ox, y - oy) for x, y in path["parcelPts"]])
    else:
        sel_poly = None

    def overlay(p, c):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if sel_poly is not None:
            p.save()
            p.setTransform(c.transform())
            pen = QPen(QColor("#159895"), 2.6)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(21, 152, 149, 70))
            p.drawPolygon(sel_poly)
            p.restore()
        w = path.get("w") or 6
        for P in path.get("roads") or []:
            c.stroke(p, _rel(P, ox, oy), COLORS["road"], width_m=w, px=2)
            c.label_at(p, _rel(P, ox, oy), f"شارع {geo.length(P):.1f} م", COLORS["road"])
        for kind, name in (("wallsR", "جدار دبش"), ("wallsC", "جدار مسلح")):
            for P in path.get(kind) or []:
                col = COLORS["wallR" if kind == "wallsR" else "wallC"]
                c.stroke(p, _rel(P, ox, oy), col, px=4, dash=kind == "wallsR")
                c.label_at(p, _rel(P, ox, oy), f"{name} {geo.length(P):.1f} م", col)
        for gg in (path.get("items") or {}).values():
            for P in gg.get("lines") or []:
                c.stroke(p, _rel(P, ox, oy), COLORS["line"], px=3)
            for P in gg.get("polys") or []:
                c.stroke(p, _rel(P, ox, oy), COLORS["area"], px=2, close=True, fill=QColor(46, 125, 50, 60))
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))
            p.setBrush(QColor(COLORS["point"]))
            for q in gg.get("points") or []:
                p.drawEllipse(c.to_screen(q[0] - ox, q[1] - oy), 5, 5)
    def overlay_all(p, c):
        overlay(p, c)
        dr = path.get("drainage")
        if dr:
            for wd in dr.get("wadis") or []:
                c.stroke(p, _rel(wd["path"], ox, oy), "#0277BD", width_m=max(wd["channel"]["width"], 1.0), px=2.5)
            for sg in dr.get("sags") or []:
                c.stroke(p, _rel(sg["path"], ox, oy), "#00ACC1", px=2.5, dash=True)
                p.setPen(QPen(QColor("#FFFFFF"), 1.5))
                p.setBrush(QColor("#0288D1"))
                p.drawEllipse(c.to_screen(sg["x"] - ox, sg["y"] - oy), 6, 6)
        sew = path.get("sewer")
        if sew:
            from ..sewer_view import STATUS_COLOR
            for lot in sew.get("lots") or []:
                col = QColor(STATUS_COLOR[lot["status"]])
                fill = QColor(col)
                fill.setAlpha(45)
                P = _rel(lot["poly"], ox, oy)
                c.stroke(p, P + P[:1], col, px=2, close=True, fill=fill)
                ln = lot.get("lane")
                if ln:
                    L = _rel(ln["path"], ox, oy)
                    c.stroke(p, L, "#8E24AA", width_m=ln["width"], px=2, dash=True)
                    c.label_at(p, L, f"دخلة خدمات {ln['length']:.0f} م", "#8E24AA")
    cv.overlay = overlay_all
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("#FFFFFF"))
    cv.render(img)
    cv.deleteLater()
    return img


__all__ = ["MapPage", "render_path_image", "share_info", "billed", "format_num"]
