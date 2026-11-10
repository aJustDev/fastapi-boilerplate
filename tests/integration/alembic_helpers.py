from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def run_alembic(connection: Connection, revision: str = "head", *, down: bool = False) -> None:
    """Run the real migrations on an open connection (see migrations/env.py)."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    if down:
        command.downgrade(cfg, revision)
    else:
        command.upgrade(cfg, revision)
