# =============================================================================
# 🧭 Heading Check and Corrections (utils/shared/heading_check.py)
# -----------------------------------------------------------------------------
# Purpose:             Find frames whose camera heading disagrees with the direction of travel,
#                      and apply per-run corrections the operator has decided
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2026-10-19
# Last Updated:        2026-10-19
#
# Description:
#   Detection is ported from rmi-rail-vision's scripts/heading_check.py (docs/HEADING_25-320.md),
#   with the same defaults. Frames are taken in capture order (day, reel, frame) and split into
#   segments at a day/reel change or where consecutive frames are more than ``gap_m`` apart. The
#   bearing of travel at a frame is the bearing from the previous frame to the next; below
#   ``min_move_m`` the vehicle is stopped and the frame is not judged. A frame is *reversed*
#   when its heading differs from travel by more than ``threshold_deg``. Runs of reversed frames
#   (``slack`` non-reversed frames allowed inside) of at least ``min_run`` frames are reported.
#
#   A reversed run is either the vehicle driving backwards (heading right; nothing to do) or a
#   wrong recorded heading. Geometry cannot tell them apart; rail-vision's sun test can. So the
#   tool detects and the operator decides: the runs CSV has an empty ``action`` column, filled
#   in and fed back as a corrections file. Actions:
#     keep        - heading is right (e.g. the hi-rail reversing)
#     flip        - heading + 180
#     from_track  - heading = travel bearing + the rig's median heading-vs-travel offset
#                   (for stretches where the recorded heading is unreliable, not a clean 180)
#     exclude     - drop the frames
#   A corrections row may name any frame range, not only a detected run.
#
# File Location:        /utils/shared/heading_check.py
# Called By:            utils/shared/oid_manifest.py, scripts/build_oid_manifest.py
# Ext. Dependencies:    none (standard library only)
# =============================================================================
from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ACTIONS = ("keep", "flip", "from_track", "exclude")
SOURCE_EXIF, SOURCE_FLIP, SOURCE_TRACK = "exif", "flip", "from_track"


@dataclass
class Frame:
    """One image, in the units the check needs. ``heading`` is degrees from north."""
    name: str
    day: str            # capture day, YYYY-MM-DD
    reel: str           # 4-digit reel
    frame: int
    lon: float
    lat: float
    heading: float
    mp: Optional[float] = None
    state: str = ""                 # edge | stopped | agrees | reversed
    diff: Optional[float] = None    # heading - travel bearing, wrapped to [-180, 180)
    travel: Optional[float] = None  # travel bearing (degrees), when judged or moving
    heading_source: str = SOURCE_EXIF
    excluded: bool = False


@dataclass
class Run:
    day: str
    reel: str
    frame_first: int
    frame_last: int
    n_frames: int
    n_reversed: int
    median_diff_deg: float
    length_m: float
    kind: str                       # "run" (>= min_run reversed) or "blip"
    mp_from: Optional[float] = None
    mp_to: Optional[float] = None
    sample_name: str = ""
    points: List[Tuple[float, float]] = field(default_factory=list, repr=False)


@dataclass
class CheckResult:
    frames: List[Frame]
    runs: List[Run]
    judged: int
    agrees: int
    stopped: int
    segments: int
    rig_offset_deg: Optional[float]     # signed median heading - travel over agreeing frames
    gap_m: float = 20.0                 # segment gap used by detect(); corrections reuse it


def _enu(lon, lat, lon0, lat0):
    k = math.cos(math.radians(lat0))
    return (lon - lon0) * 111320.0 * k, (lat - lat0) * 110574.0


def bearing_between(a: Frame, b: Frame) -> Tuple[float, float]:
    """(bearing in degrees from north, distance in metres) from a to b."""
    dx, dy = _enu(b.lon, b.lat, a.lon, a.lat)
    return math.degrees(math.atan2(dx, dy)) % 360.0, math.hypot(dx, dy)


def wrap(d: float) -> float:
    return (d + 180.0) % 360.0 - 180.0


def capture_order(frames: Iterable[Frame]) -> List[Frame]:
    return sorted(frames, key=lambda f: (f.day, f.reel, f.frame))


def segments(frames: Sequence[Frame], gap_m: float) -> List[List[Frame]]:
    segs: List[List[Frame]] = []
    cur: List[Frame] = []
    for f in frames:
        if cur:
            p = cur[-1]
            if f.day != p.day or f.reel != p.reel or bearing_between(p, f)[1] > gap_m:
                segs.append(cur)
                cur = []
        cur.append(f)
    if cur:
        segs.append(cur)
    return segs


def detect(frames: Iterable[Frame], gap_m: float = 20.0, min_move_m: float = 2.0, min_run: int = 5,
           slack: int = 3, threshold_deg: float = 135.0) -> CheckResult:
    """Judge every frame against travel and list reversed runs (rail-vision's method)."""
    ordered = capture_order(frames)
    segs = segments(ordered, gap_m)
    judged = agrees = stopped = 0
    ok_diffs: List[float] = []
    for seg in segs:
        for i, f in enumerate(seg):
            if 0 < i < len(seg) - 1:
                brg, d = bearing_between(seg[i - 1], seg[i + 1])
                if d >= min_move_m:
                    f.travel = brg
            if i == 0 or i == len(seg) - 1:
                f.state = "edge"
                continue
            if f.travel is None:
                f.state = "stopped"
                stopped += 1
                continue
            f.diff = wrap(f.heading - f.travel)
            judged += 1
            if abs(f.diff) > threshold_deg:
                f.state = "reversed"
            else:
                f.state = "agrees"
                agrees += 1
                ok_diffs.append(f.diff)

    runs: List[Run] = []
    for seg in segs:
        i = 0
        while i < len(seg):
            if seg[i].state != "reversed":
                i += 1
                continue
            j, last, miss = i, i, 0
            while j + 1 < len(seg) and miss <= slack:
                j += 1
                if seg[j].state == "reversed":
                    last, miss = j, 0
                else:
                    miss += 1
            run = seg[i:last + 1]
            rev = [f for f in run if f.state == "reversed"]
            mps = [f.mp for f in run if f.mp is not None]
            runs.append(Run(
                day=run[0].day, reel=run[0].reel, frame_first=run[0].frame, frame_last=run[-1].frame,
                n_frames=len(run), n_reversed=len(rev),
                median_diff_deg=round(statistics.median(abs(f.diff or 0.0) for f in rev), 1),
                length_m=round(sum(bearing_between(run[k], run[k + 1])[1] for k in range(len(run) - 1))),
                kind="run" if len(rev) >= min_run else "blip",
                mp_from=round(min(mps), 3) if mps else None, mp_to=round(max(mps), 3) if mps else None,
                sample_name=run[len(run) // 2].name, points=[(f.lon, f.lat) for f in run]))
            i = last + 1

    offset = round(statistics.median(ok_diffs), 2) if ok_diffs else None
    return CheckResult(ordered, runs, judged, agrees, stopped, len(segs), offset, gap_m)


# --- reports ----------------------------------------------------------------------------------

RUN_COLUMNS = ["day", "reel", "frame_first", "frame_last", "n_frames", "n_reversed", "median_diff_deg",
               "length_m", "kind", "mp_from", "mp_to", "sample_name", "action", "note"]


def write_runs_csv(runs: Sequence[Run], path: Path) -> Path:
    """Runs (detected 'run's first) with empty ``action``/``note`` columns for the operator."""
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=RUN_COLUMNS)
        w.writeheader()
        for r in sorted(runs, key=lambda r: (r.kind != "run", r.day, r.reel, r.frame_first)):
            w.writerow({"day": r.day, "reel": r.reel, "frame_first": r.frame_first, "frame_last": r.frame_last,
                        "n_frames": r.n_frames, "n_reversed": r.n_reversed, "median_diff_deg": r.median_diff_deg,
                        "length_m": r.length_m, "kind": r.kind, "mp_from": "" if r.mp_from is None else r.mp_from,
                        "mp_to": "" if r.mp_to is None else r.mp_to, "sample_name": r.sample_name,
                        "action": "", "note": ""})
    return path


def write_runs_kml(runs: Sequence[Run], path: Path, title: str = "Heading check") -> Path:
    from xml.sax.saxutils import escape
    k = ['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
         f"<name>{escape(title)}</name>",
         '<Style id="run"><LineStyle><color>ff0000ff</color><width>6</width></LineStyle></Style>',
         '<Style id="blip"><LineStyle><color>ff00a5ff</color><width>4</width></LineStyle></Style>']
    for r in runs:
        pts = r.points if len(r.points) > 1 else r.points + [(r.points[0][0] + 1e-5, r.points[0][1])]
        coords = " ".join(f"{x:.7f},{y:.7f},0" for x, y in pts)
        desc = (f"{r.day} reel {r.reel} frames {r.frame_first}-{r.frame_last}: {r.n_reversed} of {r.n_frames} "
                f"reversed, median {r.median_diff_deg} deg, {r.length_m} m; sample {r.sample_name}")
        k.append(f"<Placemark><name>{escape(f'{r.day} RL{r.reel} {r.frame_first}-{r.frame_last}')}</name>"
                 f"<styleUrl>#{r.kind}</styleUrl><description>{escape(desc)}</description>"
                 f"<LineString><coordinates>{coords}</coordinates></LineString></Placemark>")
    k.append("</Document></kml>")
    Path(path).write_text("".join(k), encoding="utf-8")
    return Path(path)


# --- corrections --------------------------------------------------------------------------------

@dataclass
class Correction:
    day: str
    reel: str
    frame_first: int
    frame_last: int
    action: str
    note: str = ""

    def covers(self, f: Frame) -> bool:
        return f.day == self.day and f.reel == self.reel and self.frame_first <= f.frame <= self.frame_last


def load_corrections(path: Path) -> List[Correction]:
    """Read a corrections CSV (the runs CSV with ``action`` filled in, or hand-written rows with
    day, reel, frame_first, frame_last, action). Rows with an empty action are ignored."""
    out: List[Correction] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            action = (row.get("action") or "").strip().lower()
            if not action:
                continue
            if action not in ACTIONS:
                raise ValueError(f"{path}, line {n}: action {action!r} is not one of {', '.join(ACTIONS)}")
            out.append(Correction(day=row["day"].strip(), reel=str(row["reel"]).strip().zfill(4),
                                  frame_first=int(row["frame_first"]), frame_last=int(row["frame_last"]),
                                  action=action, note=(row.get("note") or "").strip()))
    return out


def _fill_track(frames: List[Frame]) -> Dict[int, float]:
    """Travel bearing for every frame of one segment: its own where moving, else the nearest
    moving frame's (stopped and edge frames inherit; on a tie, the earlier one)."""
    n = len(frames)
    prev: List[Optional[int]] = [None] * n
    nxt: List[Optional[int]] = [None] * n
    last = None
    for i in range(n):
        if frames[i].travel is not None:
            last = i
        prev[i] = last
    last = None
    for i in range(n - 1, -1, -1):
        if frames[i].travel is not None:
            last = i
        nxt[i] = last
    out: Dict[int, float] = {}
    for i in range(n):
        a, b = prev[i], nxt[i]
        if a is None and b is None:
            continue
        j = a if b is None or (a is not None and i - a <= b - i) else b
        out[i] = frames[j].travel
    return out


def apply_corrections(result: CheckResult, corrections: Sequence[Correction]) -> Dict[str, int]:
    """Apply the operator's decisions to ``result.frames`` in place. Returns counts per action.

    ``from_track`` uses the travel bearing plus ``result.rig_offset_deg`` (the signed median
    heading-vs-travel difference over agreeing frames). Bearings are looked up within the segments
    detect() used, never across a gap. A frame with no travel bearing in its segment, or any
    frame when the rig offset is unknown (no agreeing frames), keeps its recorded heading and is
    reported under ``from_track_unresolved``.
    """
    counts = {a: 0 for a in ACTIONS}
    counts["from_track_unresolved"] = 0
    offset = result.rig_offset_deg
    by_segment = segments(result.frames, gap_m=result.gap_m)
    for seg in by_segment:
        track = None
        for i, f in enumerate(seg):
            c = next((c for c in corrections if c.covers(f)), None)
            if c is None:
                continue
            counts[c.action] += 1
            if c.action == "flip":
                f.heading = round((f.heading + 180.0) % 360.0, 3)
                f.heading_source = SOURCE_FLIP
            elif c.action == "from_track":
                if track is None:
                    track = _fill_track(seg)
                if offset is not None and i in track:
                    f.heading = round((track[i] + offset) % 360.0, 3)
                    f.heading_source = SOURCE_TRACK
                else:
                    counts["from_track_unresolved"] += 1
            elif c.action == "exclude":
                f.excluded = True
    return counts
