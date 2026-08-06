from sdr_recorder.database import Database
from sdr_recorder.models import FrequencyCreate


def test_database_seeds_sixteen_pmr_channels(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialise()
    rows = database.frequencies()
    assert len(rows) == 16
    assert rows[0]["frequency_hz"] == 446_006_250
    assert rows[-1]["frequency_hz"] == 446_193_750
    assert [row["name"] for row in rows if row["enabled"]] == ["PMR446 Ch13"]


def test_frequency_crud(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialise()
    item = FrequencyCreate(frequency_hz=449_400_000, name="Test", category="449 MHz")
    row = database.add_frequency(item)
    assert row["name"] == "Test"
    item.name = "Updated"
    assert database.update_frequency(row["id"], item)["name"] == "Updated"
    assert database.delete_frequency(row["id"])
