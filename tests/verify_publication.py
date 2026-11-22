import json, io, bisect
import requests
from PIL import Image
import numpy as np
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import swat_vector_time_pipeline as m

parser = argparse.ArgumentParser(
    description="Check the published Yanjiga example against its original records"
)
parser.add_argument("-c", "--config", required=True)
cfg = m.load_yaml(parser.parse_args().config)
t = Path(cfg["task"]["swat_dir"])
config_js = Path(cfg["output"]["geoserver_config_js"])
ds = json.loads(
    config_js.read_text(encoding="utf-8").split(" = ", 1)[1].strip().rstrip(";")
)

if cfg["task"]["name"] != "yanjiga" or cfg["publish"]["workspace"] != "swat":
    raise ValueError(
        "This article regression uses the bundled yanjiga task and swat workspace"
    )
db = m.pg_connect(cfg["database"])
cur = db.cursor()
r = requests.Session()
r.trust_env = False
audit = {}
lines = (t / "output.hru").read_text().splitlines()
audit["changed"] = [
    sum(float(x[a:b]) != float(x[a + 4 : b]) for x in lines[9:])
    for a, b in [(204, 214), (324, 334)]
]


def scale(v, k):
    return next(s for s in ds[v]["scales_info"] if s["scale"] == k)


def wms(v, k, date, bbox=None, size=(931, 1000)):
    entry = ds[v]
    sc = scale(v, k)
    meta = entry["url_info"]
    p = dict(
        service="WMS",
        version="1.1.1",
        request="GetMap",
        layers="swat:" + sc["layers"],
        styles="swat:" + sc["styles"],
        srs="EPSG:4326",
        bbox=bbox or meta["bbox"],
        width=size[0],
        height=size[1],
        format="image/png",
        transparent="true",
        tiled="false",
        viewparams=f"sim_time:{date};scale:{k}",
    )
    resp = r.get(meta["base_url"], params=p, timeout=30)
    resp.raise_for_status()
    if not resp.content.startswith(b"\x89PNG"):
        raise ValueError(resp.text[:1500])
    return resp.content


audit["records"] = []
for line, v, k, date in [
    (11664, "surq_gen", "monthly", "2011-07-01"),
    (12016, "syld", "monthly", "2011-07-01"),
    (14052, "syld", "yearly", "2011-01-01"),
]:
    raw = lines[line - 1]
    gis = raw[10:19]
    val = float(raw[204:214] if v == "surq_gen" else raw[324:334])
    ipr = 0 if k == "monthly" else 2
    sc = scale(v, k)
    cur.execute(
        f"SELECT h.{v},ST_X(ST_PointOnSurface(a.geom)),ST_Y(ST_PointOnSurface(a.geom)) FROM swat_hru_timeseries h JOIN swat_aoi_vector a ON a.hru_gis=h.gis AND a.task_name=h.task_name WHERE h.gis=%s AND h.iprint=%s AND h.sim_time=%s AND h.task_name=%s",
        (gis, ipr, date, "yanjiga"),
    )
    result = cur.fetchone()
    assert result
    dbv, x, y = result
    resp = r.get(
        cfg["geoserver"]["url"] + "/swat/ows",
        params=dict(
            service="WFS",
            version="1.0.0",
            request="GetFeature",
            typeName="swat:" + sc["layers"],
            outputFormat="application/json",
            propertyName="gis," + v,
            viewparams=f"sim_time:{date};scale:{k}",
            cql_filter=f"gis='{gis}'",
        ),
        timeout=30,
    )
    features = resp.json()["features"]
    assert len(features) == 1
    wfs = features[0]["properties"][v]
    assert val == dbv == wfs, (line, val, dbv, wfs)
    i = bisect.bisect_left(sc["levels"], val)
    d = 0.00001
    png = wms(v, k, date, ",".join(map(str, (x - d, y - d, x + d, y + d))), (33, 33))
    rgb = Image.open(io.BytesIO(png)).convert("RGBA").getpixel((16, 16))
    colour = sc["colors"][i]
    expected = tuple(bytes.fromhex(colour[1:]))
    assert rgb[3] > 200 and max(abs(a - b) for a, b in zip(rgb, expected)) <= 2, (
        rgb,
        expected,
    )
    audit["records"].append(
        [
            line,
            gis,
            date,
            v,
            k,
            val,
            dbv,
            wfs,
            i + 1,
            sc["levels"][i - 1],
            sc["levels"][i],
            colour,
        ]
    )
s = scale("syld", "yearly")
boundary = s["levels"][-2]
cur.execute(
    "SELECT gis, sim_year,syld FROM swat_hru_timeseries WHERE task_name='yanjiga' AND iprint=2 AND sim_year IN (2012,2015) AND syld>%s ORDER BY gis,sim_year",
    (boundary,),
)
rows = cur.fetchall()
a = {gid: v for gid, y, v in rows if y == 2012}
b = {gid: v for gid, y, v in rows if y == 2015}
audit["persistence"] = [
    len(a),
    len(b),
    [[i, a[i], b[i]] for i in sorted(a.keys() & b.keys())],
    boundary,
]
cur.execute(
    "SELECT count(*),count(*) filter(where surq_gen=0) FROM swat_hru_timeseries WHERE task_name='yanjiga' AND iprint=0"
)
audit["zero"] = cur.fetchone()
for v in ds:
    for sc in ds[v]["scales_info"]:
        cur.execute(
            f"SELECT {v} FROM swat_hru_timeseries WHERE task_name='yanjiga' AND iprint=%s",
            (0 if sc["scale"] == "monthly" else 2,),
        )
        vals = [x[0] for x in cur]
        cnt = np.bincount(np.searchsorted(sc["levels"], vals))
        assert len(cnt) == len(sc["levels"]) and min(cnt) > 0
        audit[v + sc["scale"]] = [sc["levels"], cnt.tolist()]
print(json.dumps(audit, indent=2))
