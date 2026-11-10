import uuid

import pytest

from app.cli import build_parser


class TestParser:
    def test_create_admin(self):
        args = build_parser().parse_args(["create-admin", "--email", "root@example.com"])
        assert (args.command, args.email, args.username) == (
            "create-admin",
            "root@example.com",
            None,
        )

    def test_the_password_is_never_an_argument(self):
        # It would stay in the shell history and show in the process list.
        with pytest.raises(SystemExit):
            build_parser().parse_args(["create-admin", "--email", "a@b.c", "--password", "x"])

    def test_outbox_replay_of_some_ids(self):
        first, second = uuid.uuid4(), uuid.uuid4()
        args = build_parser().parse_args(
            ["outbox", "replay", "--id", str(first), "--id", str(second), "--reset-handlers"]
        )
        assert (args.action, args.ids, args.reset_handlers) == ("replay", [first, second], True)

    def test_outbox_replay_of_everything(self):
        args = build_parser().parse_args(["outbox", "replay"])
        assert (args.ids, args.reset_handlers) == (None, False)

    def test_outbox_cleanup(self):
        assert build_parser().parse_args(["outbox", "cleanup", "--days", "7"]).days == 7

    def test_worker(self):
        assert build_parser().parse_args(["worker"]).command == "worker"

    def test_a_command_is_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])
