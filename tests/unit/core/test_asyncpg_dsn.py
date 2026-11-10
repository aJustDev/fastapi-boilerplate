from app.core import db


def test_the_listener_dsn_is_the_engine_url_without_the_driver(monkeypatch):
    monkeypatch.setattr(db.settings, "DATABASE_URL", "postgresql+asyncpg://u:p%40ss@host:6432/app")
    assert db.build_asyncpg_dsn() == "postgresql://u:p%40ss@host:6432/app"


def test_tls_is_spelled_the_way_asyncpg_reads_it(monkeypatch):
    # `ssl=` is the dialect's connect argument; a DSN parsed by asyncpg wants `sslmode=`.
    monkeypatch.setattr(
        db.settings, "DATABASE_URL", "postgresql+asyncpg://u:p@host/app?ssl=require"
    )
    assert db.build_asyncpg_dsn() == "postgresql://u:p@host/app?sslmode=require"
