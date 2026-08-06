from datetime import datetime, timezone

from sdr_recorder.util import recording_path, safe_name, within


def test_safe_filename_and_date_tree(tmp_path):
    when = datetime(2026, 8, 6, 11, 42, 18, tzinfo=timezone.utc)
    path = recording_path(tmp_path, when, "PMR446 Ch3 / unsafe", 446_031_250)
    assert path.name == "2026-08-06_11-42-18_PMR446-Ch3-unsafe_446.03125MHz.wav"
    assert path.parent == tmp_path / "2026" / "08" / "06"
    assert within(path, tmp_path)
    assert safe_name("../../") == "recording"
