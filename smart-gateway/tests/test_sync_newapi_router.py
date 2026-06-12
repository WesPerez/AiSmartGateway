from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


def load_sync_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "sync-newapi-router.py"
    spec = importlib.util.spec_from_file_location("sync_newapi_router", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def make_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("create table options (key text primary key, value text)")
    con.execute(
        """
        create table models (
            id integer primary key,
            model_name text not null,
            tags text,
            status integer default 1,
            deleted_at datetime,
            updated_time integer,
            created_time integer,
            description text,
            icon text,
            vendor_id integer,
            endpoints text,
            sync_official integer,
            name_rule integer
        )
        """
    )
    return con


def test_sync_model_ratio_keeps_only_active_models_and_archives_prices(tmp_path):
    sync = load_sync_module()
    con = make_db(tmp_path / "one-api.db")
    con.execute(
        "insert into options (key, value) values ('ModelRatio', ?)",
        (json.dumps({"old-model": 2.5, "gpt-5.5": 0.5}),),
    )

    added, removed = sync.sync_model_ratio(con, "gpt-5.5,new-model")
    ratios = sync.load_json_option(con, "ModelRatio")
    archive = sync.load_json_option(con, "SmartGatewayModelRatioArchive")

    assert added == 1
    assert removed == 1
    assert set(ratios) == {"gpt-5.5", "new-model"}
    assert archive["old-model"] == 2.5

    sync.sync_model_ratio(con, "old-model")
    restored = sync.load_json_option(con, "ModelRatio")
    assert restored == {"old-model": 2.5}


def test_sync_models_table_auto_hides_and_restores_gateway_models(tmp_path):
    sync = load_sync_module()
    con = make_db(tmp_path / "one-api.db")
    con.execute(
        "insert into models (model_name, tags, status, deleted_at) values ('gone-model', 'smart-gateway', 1, null)"
    )

    sync.sync_models_table(con, "active-model")
    rows = {
        row["model_name"]: dict(row)
        for row in con.execute("select model_name, tags, status from models where deleted_at is null").fetchall()
    }
    assert rows["gone-model"]["status"] == 0
    assert "smart-gateway-auto-disabled" in rows["gone-model"]["tags"]
    assert rows["active-model"]["status"] == 1

    assert sync.disabled_models(con) == set()

    sync.sync_models_table(con, "gone-model")
    restored = con.execute(
        "select tags, status from models where model_name = 'gone-model' and deleted_at is null"
    ).fetchone()
    assert restored["status"] == 1
    assert "smart-gateway-auto-disabled" not in restored["tags"]
