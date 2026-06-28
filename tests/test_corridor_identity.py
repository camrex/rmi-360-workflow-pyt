"""Unit tests for panorama filename identity parsing (reel, reel_start_ts, frame).
The reel START timestamp — not the reel number — is the reliable cross-reel
ordering key (battery/power-cycle bug safe). No arcpy required."""

from utils.corridor.units import (
    compile_identity_regex,
    parse_reel_frame,
    parse_run_frame,
    tkey,
)

SAMPLE = "pano_reel_0023_20260619-160716_26-150_000037.jpg"


def test_parse_run_frame_default_regex():
    regex = compile_identity_regex()
    run, frame = parse_run_frame(SAMPLE, regex)
    assert run == ("0023", "20260619-160716")
    assert frame == 37


def test_parse_reel_frame_components():
    regex = compile_identity_regex()
    reel, rts, frame = parse_reel_frame(SAMPLE, regex)
    assert reel == "0023"
    assert rts == "20260619-160716"
    assert frame == 37


def test_project_tag_is_free_wildcard():
    # The middle tag can be anything; identity still parses.
    regex = compile_identity_regex()
    name = "pano_reel_0001_20250101-000000_ANYTHING-HERE_000999.jpg"
    run, frame = parse_run_frame(name, regex)
    assert run == ("0001", "20250101-000000")
    assert frame == 999


def test_case_insensitive_extension():
    regex = compile_identity_regex()
    run, frame = parse_run_frame(SAMPLE.replace(".jpg", ".JPG"), regex)
    assert run == ("0023", "20260619-160716")
    assert frame == 37


def test_non_matching_returns_none():
    regex = compile_identity_regex()
    assert parse_run_frame("not_a_pano.png", regex) == (None, None)
    assert parse_reel_frame("not_a_pano.png", regex) is None
    assert parse_run_frame(None, regex) == (None, None)


def test_same_reel_number_distinguished_by_start_ts():
    # The battery-bug scenario: same reel NUMBER, different capture runs.
    regex = compile_identity_regex()
    a, _ = parse_run_frame("pano_reel_0001_20260101-080000_p_000001.jpg", regex)
    b, _ = parse_run_frame("pano_reel_0001_20260105-093000_p_000001.jpg", regex)
    assert a != b  # distinct runs despite identical reel number


def test_tkey_sentinel():
    assert tkey(None) == "_main"
    assert tkey("") == "_main"
    assert tkey(4) == "4"
    assert tkey("4") == "4"
