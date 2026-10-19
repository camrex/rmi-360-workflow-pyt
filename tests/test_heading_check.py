"""Unit tests for utils/shared/heading_check.py — reversed-heading detection and corrections.
Loaded by file path: the module is pure standard library (no arcpy)."""

import importlib.util
import math
import pathlib
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    "heading_check_under_test",
    pathlib.Path(__file__).resolve().parents[1] / "utils" / "shared" / "heading_check.py")
hc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = hc          # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(hc)

LAT0, LON0 = 41.88, -87.64
M_PER_DEG_LAT = 110574.0


def track(n, heading, step_m=4.0, day="2025-10-20", reel="0003", start=1, bearing=0.0, offset=0.0):
    """n frames driving along ``bearing`` (degrees) at step_m spacing, each with ``heading``."""
    out = []
    k = math.cos(math.radians(LAT0))
    for i in range(n):
        d = i * step_m
        dy, dx = d * math.cos(math.radians(bearing)), d * math.sin(math.radians(bearing))
        out.append(hc.Frame(name=f"RL{reel}_FR{start + i:06d}.jpg", day=day, reel=reel, frame=start + i,
                            lon=LON0 + dx / (111320.0 * k), lat=LAT0 + dy / M_PER_DEG_LAT,
                            heading=(heading + offset) % 360))
    return out


def test_agreeing_track_has_no_runs_and_measures_rig_offset():
    res = hc.detect(track(50, heading=0.0, offset=1.8))
    assert res.runs == []
    assert res.judged == 48 and res.agrees == 48
    assert res.rig_offset_deg == pytest.approx(1.8, abs=0.05)


def test_reversed_stretch_is_one_run():
    frames = track(20, 0.0) + track(30, 180.0, start=21)
    # continue the same line northwards so positions stay consecutive
    for i, f in enumerate(frames):
        f.lat = LAT0 + i * 4.0 / M_PER_DEG_LAT
        f.lon = LON0
    res = hc.detect(frames)
    runs = [r for r in res.runs if r.kind == "run"]
    assert len(runs) == 1
    r = runs[0]
    assert (r.frame_first, r.frame_last) == (21, 49)   # last frame is a segment edge, not judged
    assert r.median_diff_deg == pytest.approx(180.0, abs=0.5)


def test_short_reversal_is_a_blip():
    frames = track(30, 0.0)
    for f in frames[10:13]:
        f.heading = 180.0
    res = hc.detect(frames)
    assert [r.kind for r in res.runs] == ["blip"]


def test_stopped_frames_are_not_judged():
    frames = track(10, 0.0, step_m=0.5)                 # 1 m prev-to-next: below min_move 2 m
    res = hc.detect(frames)
    assert res.judged == 0 and res.stopped == 8


def test_gap_splits_segments():
    a = track(10, 0.0)
    b = track(10, 0.0, start=11)
    for f in b:
        f.lat += 1000.0 / M_PER_DEG_LAT                 # 1 km jump
    res = hc.detect(a + b)
    assert res.segments == 2


def test_corrections_flip_track_exclude(tmp_path):
    frames = track(40, 180.0, offset=0.0)               # recorded heading points behind travel
    res = hc.detect(track(60, 0.0, reel="0001", offset=2.0) + frames)
    assert res.rig_offset_deg == pytest.approx(2.0, abs=0.05)
    csv_path = tmp_path / "corr.csv"
    csv_path.write_text(
        "day,reel,frame_first,frame_last,action,note\n"
        "2025-10-20,3,1,10,flip,\n"
        "2025-10-20,0003,11,30,from_track,unreliable\n"
        "2025-10-20,0003,31,35,exclude,\n"
        "2025-10-20,0003,36,40,,undecided\n", encoding="utf-8")
    corr = hc.load_corrections(csv_path)
    assert [c.action for c in corr] == ["flip", "from_track", "exclude"]
    counts = hc.apply_corrections(res, corr)
    assert counts["flip"] == 10 and counts["from_track"] == 20 and counts["exclude"] == 5
    by = {(f.reel, f.frame): f for f in res.frames}
    assert by[("0003", 5)].heading == pytest.approx(0.0, abs=1e-6) and by[("0003", 5)].heading_source == "flip"
    t = by[("0003", 20)]
    assert t.heading_source == "from_track" and t.heading == pytest.approx(2.0, abs=0.1)  # travel 0 + offset
    edge = by[("0003", 11)]
    assert edge.heading_source == "from_track"                                   # inherits a neighbour
    assert by[("0003", 33)].excluded and not by[("0003", 37)].excluded
    assert by[("0003", 37)].heading == pytest.approx(180.0) and by[("0003", 37)].heading_source == "exif"


def _corr(reel, first, last, action="from_track", day="2025-10-20"):
    return hc.Correction(day=day, reel=reel, frame_first=first, frame_last=last, action=action)


def test_from_track_does_not_borrow_across_a_gap():
    a = track(20, 0.0, reel="0003")
    b = track(5, 90.0, reel="0003", start=21, step_m=0.2)       # stopped stretch 1 km away
    for f in b:
        f.lat += 1000.0 / M_PER_DEG_LAT
    res = hc.detect(track(30, 0.0, reel="0001") + a + b)
    counts = hc.apply_corrections(res, [_corr("0003", 21, 25)])
    assert counts["from_track_unresolved"] == 5
    assert all(f.heading == pytest.approx(90.0) and f.heading_source == "exif"
               for f in res.frames if f.reel == "0003" and f.frame > 20)


def test_from_track_needs_a_rig_offset():
    res = hc.detect(track(20, 180.0))                           # nothing agrees: offset unknown
    assert res.rig_offset_deg is None
    counts = hc.apply_corrections(res, [_corr("0003", 1, 20)])
    assert counts["from_track"] == 20 and counts["from_track_unresolved"] == 20
    assert all(f.heading == pytest.approx(180.0) and f.heading_source == "exif" for f in res.frames)


def test_fill_track_takes_the_nearest_moving_frame():
    fs = track(9, 0.0)
    for f in fs:
        f.travel = None
    fs[2].travel, fs[6].travel = 10.0, 20.0
    got = hc._fill_track(fs)
    assert [got[i] for i in range(9)] == [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0, 20.0]  # tie -> earlier
    for f in fs:
        f.travel = None
    assert hc._fill_track(fs) == {}


def test_bad_action_is_rejected(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("day,reel,frame_first,frame_last,action\n2025-10-20,1,1,2,rotate\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rotate"):
        hc.load_corrections(p)


def test_runs_csv_and_kml_round_trip(tmp_path):
    frames = track(20, 0.0) + track(30, 180.0, start=21)
    for i, f in enumerate(frames):
        f.lat = LAT0 + i * 4.0 / M_PER_DEG_LAT
        f.lon = LON0
    res = hc.detect(frames)
    import csv
    p = hc.write_runs_csv(res.runs, tmp_path / "runs.csv")
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    rows[0]["action"] = "flip"                                        # the operator decides run 1
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    corr = hc.load_corrections(p)
    assert corr and corr[0].action == "flip" and corr[0].reel == "0003"
    k = hc.write_runs_kml(res.runs, tmp_path / "runs.kml")
    assert "<LineString>" in k.read_text(encoding="utf-8")
