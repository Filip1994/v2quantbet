from h2h.migrate import _migration_dir


def test_migration_directory_prefers_container_working_tree(tmp_path, monkeypatch) -> None:
    expected = tmp_path / "migrations"
    expected.mkdir()
    monkeypatch.chdir(tmp_path)

    assert _migration_dir() == expected
