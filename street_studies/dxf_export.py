"""ملف DXF لمسار مواطن: القطعة المحددة، والمحيط من المخطط التنظيمي، والشارع والجدران والبنود — بإحداثيات JTM."""
import ezdxf
from PySide6.QtCore import QRectF

LAYERS = {
    "Parcel_Selected": 4, "Org_Parcel": 2, "Org_Street": 1, "Org_Wadi": 5, "Sharee": 30,
    "Judran_Dabsh_Batoun": 32, "Judran_Musallah": 8, "Notes": 7,
}


def _layer_for_code(code):
    return "Item_" + "".join(ch if ch.isalnum() else "_" for ch in code)


def write_path_dxf(path, name, out_file):
    doc = ezdxf.new("R2010", setup=True)
    doc.styles.add("ARABIC", font="arial.ttf")
    for lname, color in LAYERS.items():
        doc.layers.add(lname, color=color)
    msp = doc.modelspace()

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
            names = {geo.LAYER_PARCEL: "Org_Parcel", geo.LAYER_ROAD: "Org_Street", geo.LAYER_WADI: "Org_Wadi"}
            for ds in g.datasets:
                for i, r in enumerate(ds.bbox):
                    if not r.intersects(box):
                        continue
                    layer = names.get(ds.layers[i], "Org_Parcel")
                    P = ds.abs_points(i)
                    closed = ds.layers[i] == geo.LAYER_PARCEL
                    msp.add_lwpolyline(P, close=closed, dxfattribs={"layer": layer})
                    if closed and ds.nums[i]:
                        c = r.center()
                        msp.add_text(ds.nums[i], height=1.2, dxfattribs={"layer": "Org_Parcel"}) \
                            .set_placement((c.x() + g.ox, c.y() + g.oy), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        except Exception:  # noqa: BLE001
            pass

    if path.get("parcelPts"):
        msp.add_lwpolyline(path["parcelPts"], close=True, dxfattribs={"layer": "Parcel_Selected", "lineweight": 50})
    w = float(path.get("w") or 6)
    for P in path.get("roads") or []:
        msp.add_lwpolyline(P, dxfattribs={"layer": "Sharee", "const_width": w})
    for P in path.get("wallsR") or []:
        msp.add_lwpolyline(P, dxfattribs={"layer": "Judran_Dabsh_Batoun", "const_width": 0.3})
    for P in path.get("wallsC") or []:
        msp.add_lwpolyline(P, dxfattribs={"layer": "Judran_Musallah", "const_width": 0.3})
    for code, gg in (path.get("items") or {}).items():
        ln = _layer_for_code(code)
        if ln not in doc.layers:
            doc.layers.add(ln, color=3)
        for P in gg.get("lines") or []:
            msp.add_lwpolyline(P, dxfattribs={"layer": ln})
        for P in gg.get("polys") or []:
            msp.add_lwpolyline(P, close=True, dxfattribs={"layer": ln})
        for q in gg.get("points") or []:
            msp.add_point(q, dxfattribs={"layer": ln})
            msp.add_circle(q, 0.4, dxfattribs={"layer": ln})

    anchor = (path.get("parcelPts") or pts or [[0, 0]])[0]
    msp.add_text(f"Name: {name}", height=2.0, dxfattribs={"layer": "Notes", "style": "ARABIC"}) \
        .set_placement((anchor[0], anchor[1] + 6))
    msp.add_text(f"Parcel: {path.get('parcel') or ''}  Road: {path.get('bill', 0):.2f} m x {w:g} m",
                 height=1.5, dxfattribs={"layer": "Notes"}).set_placement((anchor[0], anchor[1] + 3))
    doc.saveas(out_file)
