"""Operations that are not HTTP requests: `python -m app.cli <command>`.

It ships in the Docker image (`docker run --entrypoint python <image> -m app.cli ...`) and
reads the same settings as the API.

    create-admin --email E --username U    first administrator, or promote an account
    outbox replay [--id UUID ...]          FAILED events back to PENDING
    outbox cleanup [--days N]              delete old PROCESSED events now
    worker                                 outbox and job workers, without the API
"""

import argparse
import asyncio
import getpass
import logging
import os
import signal
import sys
import uuid
from collections.abc import Sequence

import app.db_registry as _db_registry  # noqa: F401 -- models, event handlers and jobs
from app.auth.models.user import UserORM
from app.auth.repos.user import UserRepo
from app.auth.schemas.token import RegisterRequest
from app.core.db import async_session_factory, engine
from app.core.events.cleanup import cleanup_processed_events, replay_failed_events
from app.core.events.worker import OutboxWorker
from app.core.jobs.worker import JobWorker
from app.core.logging.config import setup_logging
from app.core.security import hash_password

logger = logging.getLogger(__name__)

ADMIN_ROLE = "admin"


async def create_admin(email: str, username: str, password: str | None) -> str:
    """Create an account with the admin role, or give the role to the account with that email.

    Self-registration only grants the `user` role, and nothing in the API hands out
    roles: this is how the first administrator of a deployment comes to exist.
    """
    async with async_session_factory() as session:
        repo = UserRepo(session)
        role = await repo.get_role(ADMIN_ROLE)
        if role is None:
            raise SystemExit(f"role {ADMIN_ROLE!r} is missing: run `alembic upgrade head` first")

        user = await repo.get_by_email(email)
        if user is not None:
            if user.has_role(ADMIN_ROLE):
                return f"{user.email} is already an administrator"
            user.roles.append(role)
            await session.commit()
            return f"{user.email} is now an administrator"

        if password is None:
            raise SystemExit("a new account needs a password: set ADMIN_PASSWORD or use a terminal")
        # The same rules as POST /v1/auth/register.
        fields = RegisterRequest(email=email, username=username, password=password)
        session.add(
            UserORM(
                email=fields.email,
                username=fields.username,
                password_hash=hash_password(fields.password),
                is_active=True,
                roles=[role],
            )
        )
        await session.commit()
        return f"created administrator {fields.email}"


async def run_workers() -> None:
    """The outbox and job workers until SIGINT or SIGTERM.

    For deployments that scale the API and the workers apart: API processes run with
    OUTBOX_WORKER_ENABLED=false and JOB_WORKER_ENABLED=false, and this is the other one.
    """
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    outbox, jobs = OutboxWorker(), JobWorker()
    await outbox.start()
    await jobs.start()
    logger.info("Workers running (PID=%d)", os.getpid())
    await stop.wait()
    await jobs.stop()
    await outbox.stop()


def _password() -> str | None:
    # Never an argument: it would be visible in the process list and the shell history.
    from_env = os.environ.get("ADMIN_PASSWORD")
    if from_env:
        return from_env
    return getpass.getpass("Password: ") if sys.stdin.isatty() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="create or promote an administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--username", help="for a new account; defaults to the part before @")

    outbox = commands.add_parser("outbox", help="event bus maintenance")
    actions = outbox.add_subparsers(dest="action", required=True)
    replay = actions.add_parser("replay", help="FAILED events back to PENDING")
    replay.add_argument("--id", dest="ids", action="append", type=uuid.UUID, help="repeatable")
    replay.add_argument(
        "--reset-handlers",
        action="store_true",
        help="run every handler again, also the ones that had succeeded",
    )
    cleanup = actions.add_parser("cleanup", help="delete old PROCESSED events")
    cleanup.add_argument("--days", type=int, help="retention; default OUTBOX_CLEANUP_DAYS")

    commands.add_parser("worker", help="run the outbox and job workers")
    return parser


async def main_async(argv: Sequence[str] | None = None) -> str | None:
    """Run one command and return the line to print, if any."""
    args = build_parser().parse_args(argv)
    if args.command == "create-admin":
        username = args.username or args.email.split("@")[0]
        return await create_admin(args.email, username, _password())
    if args.command == "worker":
        await run_workers()
        return None
    if args.action == "replay":
        count = await replay_failed_events(args.ids, reset_handler_state=args.reset_handlers)
        return f"{count} event(s) back to PENDING"
    count = await cleanup_processed_events(args.days)
    return f"{count} processed event(s) deleted"


async def _run_and_close(argv: Sequence[str] | None) -> str | None:
    try:
        return await main_async(argv)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    setup_logging()
    message = asyncio.run(_run_and_close(argv))
    if message:
        print(message)  # noqa: T201 -- the output of a command


if __name__ == "__main__":
    main()
