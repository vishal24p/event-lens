from __future__ import annotations

from clean_data import clear_data


def test_clear_data_removes_selected_contents_and_preserves_directories(tmp_path):
    data_dir = tmp_path / "data"
    for name in ("audio", "normalized", "quality", "transcripts", "classifications", "reports"):
        directory = data_dir / name
        directory.mkdir(parents=True)
        (directory / "sample.json").write_text("data", encoding="utf-8")
    (data_dir / "queue.json").write_text("{}", encoding="utf-8")

    clear_data(data_dir, ("audio", "normalized", "quality", "queue.json"))

    assert (data_dir / "audio").is_dir()
    assert list((data_dir / "audio").iterdir()) == []
    assert not (data_dir / "queue.json").exists()
    assert (data_dir / "transcripts" / "sample.json").exists()


def test_clear_data_rejects_targets_outside_data_directory(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")

    try:
        clear_data(tmp_path / "data", ("..",))
    except ValueError as error:
        assert "data directory" in str(error)
    else:
        raise AssertionError("clear_data accepted a target outside data directory")

    assert outside.exists()
