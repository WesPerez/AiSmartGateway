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
        create table channels (
            id integer primary key,
            name text,
            status integer,
            base_url text,
            models text,
            tag text,
            "group" text,
            priority integer,
            weight integer,
            key text,
            type integer,
            auto_ban integer,
            test_model text,
            remark text,
            created_time integer
        )
        """
    )
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
    con.execute(
        """
        create table abilities (
            "group" text,
            model text,
            channel_id integer,
            enabled numeric,
            priority integer,
            weight integer,
            tag text,
            primary key ("group", model, channel_id)
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


def test_auto_adopt_default_channels_tags_only_enabled_plain_channels(tmp_path):
    sync = load_sync_module()
    con = make_db(tmp_path / "one-api.db")
    con.execute(
        """
        insert into channels (id, name, status, base_url, models, tag, "group", priority, weight, key)
        values
          (1, 'new-upstream', 1, 'https://new.example', 'm1', '', 'default', 0, 0, 'sk-new'),
          (2, 'disabled-upstream', 0, 'https://off.example', 'm1', '', 'default', 0, 0, 'sk-off'),
          (3, 'tagged-upstream', 1, 'https://tagged.example', 'm1', 'custom', 'default', 0, 0, 'sk-tag')
        """
    )
    args = type(
        "Args",
        (),
        {
            "db": str(tmp_path / "one-api.db"),
            "providers": str(tmp_path / "providers.yaml"),
            "env": str(tmp_path / ".env"),
            "gateway_url": "http://127.0.0.1:1",
            "router_groups": "default",
            "no_backup": True,
            "bootstrap": False,
            "auto_adopt_default_channels": True,
            "force_reload": False,
        },
    )()
    (tmp_path / ".env").write_text("MASTER_API_KEY=master\nADMIN_TOKEN=admin\n", encoding="utf-8")
    con.commit()
    con.close()

    sync.sync(args)

    con = sqlite3.connect(tmp_path / "one-api.db")
    rows = dict(con.execute("select name, tag from channels where id in (1, 2, 3)").fetchall())
    assert rows["new-upstream"] == "gateway-source,gw:opportunistic,gw:unknown"
    assert rows["disabled-upstream"] == ""
    assert rows["tagged-upstream"] == "custom"
