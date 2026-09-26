"""Measurement layer checked against the worked examples in the task brief and the live demo (img_000860)."""
import pytest

from core.data import Report
from core.geo import Footprint
from core.reports import locate
from core.scene import Scene


def test_pixel_to_geo_matches_brief_example():
    # gorev_tanimi.pdf, "Uçtan uca örnek": img_000123, 1360x765, box centre (640, 394)
    fp = Footprint(1360, 765, dict(top_left=[39.94510, 32.86200], top_right=[39.94510, 32.86519],
                                   bottom_left=[39.94373, 32.86200], bottom_right=[39.94373, 32.86519]))
    lat, lon = fp.to_geo(640, 394)
    assert lon == pytest.approx(32.86350, abs=5e-6)
    assert lat == pytest.approx(39.94439, abs=5e-6)
    assert fp.to_px((lat, lon)) == pytest.approx((640, 394), abs=1e-6)


def test_example_truck_is_matched_to_T0122():
    s = Scene("img_000860")
    row = next(r for r in s.track_matches()["matches"] if r["track_id"] == "T0122")
    assert row["cls"] == "truck" and row["dist_m"] < 1.0
    assert row["conf"] < 0.3   # weak box: whether it is real is for the agent to judge


def test_T0122_motion_matches_live_example():
    m = Scene.motion("T0122")
    assert m["dist_to_base_now_m"] == pytest.approx(1600, abs=100)          # "üsse 1,6 km"
    series = dict(m["dist_to_base_series"])
    assert series["13:10"] == pytest.approx(5475, abs=50)                   # "13:15 → 5,5 km"
    assert any(s["start"] == "12:10" and s["minutes"] == 40 for s in m["stops"])  # "12:10 · 40 dk bekledi"


def test_report_R125_located_on_the_truck():
    s = Scene("img_000860")
    r = next(r for r in s.reports()["reports"] if r["text"].startswith("39.9253N 32.8718E"))
    assert r["dist_point_to_frame_m"] == 0
    assert r["within_60m_of_point"][0]["track_id"] == "T0122"
    assert "overall" not in r and "verdict" not in r   # no verdicts in the tool layer


def test_locate():
    loc = locate(Report("X", "09:45", "official", "39.9307N 32.8380E yakininda 5 kamyonun durdugu bildirildi."))
    assert loc.coord == (39.9307, 32.8380) and loc.coord_decimals == 4
    assert locate(Report("X", "09:45", "official", "Kuzeydogu Kavsagi bolgesinde trafik normal.")).zone == "Kuzeydogu Kavsagi"


def test_every_image_has_measurements():
    from core.data import images
    for iid in images():
        s = Scene(iid)
        assert s.detections()["count"] > 0, iid
        s.track_matches(); s.reports()


def test_claim_table_for_R017():
    # "5 kamyonun durdugu": no truck near the point, and most vehicles there are moving
    r = next(x for x in Scene("img_005788").reports()["reports"] if x["rid"] == "R017")
    rows = {c["claim"].split(":")[0]: c["measurement"] for c in r["claims_vs_measurements"]}
    assert "truck: 0" in rows["tip"] and "sayı" in rows and "hareketli" in rows["hareket"]


def test_subjects():
    required, optional = Scene("img_005788").subjects()
    assert "T0223" in required and "D7" in required and optional == ["D8"]   # D7 weak but tracked, D8 weak and alone
