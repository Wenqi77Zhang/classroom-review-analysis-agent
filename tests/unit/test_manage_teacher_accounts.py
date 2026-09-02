from __future__ import annotations

import argparse

import pytest

from backend.app.models import User
from scripts.manage_teacher_accounts import (
    build_parser,
    normalize_email,
    set_account_active,
    validate_password,
)


def test_normalize_email_is_case_insensitive() -> None:
    assert normalize_email(" Teacher@Example.edu ") == "teacher@example.edu"


@pytest.mark.parametrize("value", ["missing-at.example", "a@b", "a b@example.edu"])
def test_normalize_email_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        normalize_email(value)


@pytest.mark.parametrize("value", ["short1", "allletterslong", "123456789012"])
def test_password_policy_rejects_weak_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_password(value)


def test_parser_never_accepts_password_argument() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "create",
                "--email",
                "teacher@example.edu",
                "--display-name",
                "教师",
                "--password",
                "secret-in-shell-history",
            ]
        )


def test_deactivation_revokes_old_tokens_even_after_reactivation() -> None:
    user = User(
        email="teacher@example.edu",
        display_name="教师",
        password_hash="not-used-by-this-unit-test",
        is_active=True,
        auth_version=4,
    )

    set_account_active(user, active=False)
    assert user.is_active is False
    assert user.auth_version == 5

    set_account_active(user, active=True)
    assert user.is_active is True
    assert user.auth_version == 5
