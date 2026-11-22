import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


@pytest.mark.parametrize("legacy", [False, True])
def test_attribution_upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy: bool) -> None:
    database = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    config = Config("alembic.ini")
    if legacy:
        command.upgrade(config, "7cdabea4159b")
        with sqlite3.connect(database) as connection:
            connection.execute("INSERT INTO users (tg_id, username) VALUES (987, 'example')")
    command.upgrade(config, "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT count(*) FROM dict_values").fetchone() == (13,)
        assert connection.execute("SELECT count(*) FROM lead_magnets").fetchone() == (0,)
        if legacy:
            assert connection.execute(
                "SELECT username, first_touch_id, first_seen_at = created_at FROM users"
            ).fetchone() == ("example", None, 1)
    command.downgrade(config, "7cdabea4159b")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone() == (int(legacy),)
