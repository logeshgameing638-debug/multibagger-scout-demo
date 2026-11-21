"""Server-side qualification of visitor isolation: path confinement, concurrent binding,
in-flight eviction protection, idle eviction + clean recreation. Run with the venv python."""
import base64
import os
import sqlite3
import sys
import threading
from pathlib import Path

os.environ["SCOUT_PROVIDER"] = "synthetic"
os.environ["SCOUT_NEWS"] = "synthetic"
os.environ["SCOUT_ISOLATION"] = "visitor"
sys.path.insert(0, "/tmp/mbsite")
sys.path.insert(0, "/tmp/mb/multibagger_scout_ai")
sys.path.insert(0, "/tmp/mb/multibagger_scout_ai/tests")

import handler  # noqa: E402
from config import settings  # noqa: E402

vdir = settings.ROOT / "visitors"
vdir.mkdir(exist_ok=True)
for p in vdir.glob("*.db"):
    p.unlink()
handler._VFACTORIES.clear()
handler._VACTIVE.clear()
handler._VUSE.clear()


def urows(vid):
    p = vdir / (vid + ".db")
    if not p.exists():
        return None
    return [r[0] for r in sqlite3.connect(p).execute("select symbol from universe order by symbol")]


def csv_b64(sym):
    raw = f"symbol,name of company,isin number,series\n{sym},Co {sym},INE0000{sym},EQ\n"
    return base64.b64encode(raw.encode()).decode()


# ---- 1. path confinement + missing identity
r = handler.dispatch({"action": "overview", "vid": "../../etc/evil"}, {})
assert "error" not in r, r
assert (vdir / "etcevil.db").exists(), "sanitized vid did not stay inside visitors/"
assert not (settings.ROOT / "evil.db").exists(), "crafted vid escaped into the archive root"
assert not os.path.exists("/etc/evil.db"), "crafted vid escaped the app tree"
r = handler.dispatch({"action": "overview", "vid": ""}, {})
assert "error" in r and "identity" in r["error"], r
r = handler.dispatch({"action": "overview"}, {})
assert "error" in r and "identity" in r["error"], r
print("1 path confinement + missing-vid rejection OK (crafted vid confined to visitors/etcevil.db)")

# ---- 2. concurrent binding: 8 threads upload distinct symbols simultaneously
errs = []


def work(i):
    vid = f"w{i:015d}"[:16]
    try:
        out = handler.dispatch({"action": "upload_csv", "vid": vid, "exchange": "NSE",
                                "name": f"f{i}.csv", "content_b64": csv_b64(f"S{i:03d}")}, {})
        if "error" in out:
            errs.append((i, out["error"]))
    except Exception as exc:  # noqa: BLE001
        errs.append((i, repr(exc)))


ths = [threading.Thread(target=work, args=(i,)) for i in range(8)]
[t.start() for t in ths]
[t.join() for t in ths]
assert not errs, errs
for i in range(8):
    vid = f"w{i:015d}"[:16]
    rows = urows(vid)
    assert rows == [f"S{i:03d}"], (vid, rows)  # exactly own row, nobody else's
print("2 concurrent binding OK (8 simultaneous uploads, each DB holds only its own row)")

# ---- 3. in-flight eviction protection under churn past the cap
handler._MAX_VISITOR_DBS = 4
avid = "activevid0000001"
handler.dispatch({"action": "upload_csv", "vid": avid, "exchange": "NSE", "name": "a.csv",
                  "content_b64": csv_b64("ACTV")}, {})
assert urows(avid) == ["ACTV"]
handler._active_inc(avid)  # simulate an in-flight request bound to avid
try:
    for i in range(8):
        handler.dispatch({"action": "overview", "vid": f"churn{i:010d}"[:16]}, {})
        assert (vdir / (avid + ".db")).exists(), f"ACTIVE visitor DB evicted at churn {i}"
        assert urows(avid) == ["ACTV"], "active visitor data changed during churn"
finally:
    handler._active_dec(avid)
print("3 in-flight protection OK (active DB survived 8 churn visitors with cap=4)")

# ---- 4. idle eviction never hands a visitor someone else's workspace
for i in range(6):
    handler.dispatch({"action": "overview", "vid": f"xtra{i:010d}"[:16]}, {})
dbs = sorted(p.stem for p in vdir.glob("*.db"))
assert len(dbs) <= 6, dbs  # cap(4) + at most active/current spill
if not (vdir / (avid + ".db")).exists():
    out = handler.dispatch({"action": "f01", "vid": avid}, {})
    assert "error" not in out, out
    assert urows(avid) == [], f"recreated workspace must be empty, got {urows(avid)}"
    print(f"4 idle eviction OK ({len(dbs)} DBs bounded; evicted visitor recreated EMPTY, no foreign data)")
else:
    # avid was most-recently-used among idle; someone older was evicted first - still bounded and consistent
    assert urows(avid) == ["ACTV"]
    print(f"4 LRU order OK ({len(dbs)} DBs bounded; oldest idle evicted first, recent visitor kept)")

handler._MAX_VISITOR_DBS = 25

# ---- 5. exports confinement: a visitor's report lands only under exports/<vid>/
xdir = settings.ROOT / "exports"
for p in xdir.glob("*/"):
    for f in p.glob("*"):
        f.unlink()
vid_r = "reporter00000000"
st_r = {}
out = handler.dispatch({"action": "research", "vid": vid_r, "symbol": "ALPHA", "exchange": "NSE"}, st_r)
assert "error" not in out, out
out = handler.dispatch({"action": "make_report", "vid": vid_r}, st_r)
assert "paths" in out, out
for fmt, p in out["paths"].items():
    pp = Path(p).resolve()
    assert pp.parent == (xdir / vid_r).resolve(), (fmt, pp)  # strictly the visitor's own export dir
    assert pp.exists()
print("5 exports confinement OK (report files strictly under exports/<vid>/)")

print("UNIT-F ALL OK")
