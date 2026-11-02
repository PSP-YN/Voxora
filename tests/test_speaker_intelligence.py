import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speaker_intelligence import parse_script_markup, compare_profiles


def test_sentence_markup_parses_pause_speed_delivery_and_emphasis():
    parts = parse_script_markup(
        "Start. [pause:750ms][speed:0.9]Slow phrase[/speed] "
        "[delivery:formal]Formal phrase.[/delivery] [emphasis]Important[/emphasis]",
        {"speed": 1.0},
    )
    assert any(x["type"] == "pause" and x["milliseconds"] == 750 for x in parts)
    slow = next(x for x in parts if x.get("text") == "Slow phrase")
    assert slow["speed"] == 0.9
    assert any(x.get("text") == "Formal phrase." and x["delivery"] == "formal" for x in parts)
    assert any(x.get("text") == "Important" and x["emphasis"] for x in parts)


def test_sentence_markup_restores_speed_after_tag():
    parts = parse_script_markup("[speed:0.8]slow[/speed] normal", {"speed": 1.1})
    assert parts[0]["speed"] == 0.8
    assert parts[1]["speed"] == 1.1


def test_profile_comparison_reports_deltas_without_fake_similarity_score():
    ref = {"pitch_median_hz": 150, "rms_dbfs": -20}
    out = {"pitch_median_hz": 160, "rms_dbfs": -18}
    result = compare_profiles(ref, out)
    assert result["metrics"]["pitch_median_hz"]["difference"] == 10
    assert "similarity_score" not in result
