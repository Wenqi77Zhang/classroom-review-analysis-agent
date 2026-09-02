"""Safely create and maintain formal teacher accounts.

Passwords are read with ``getpass`` so they never enter shell history, process
arguments, repository files, or normal logs. Run this command only from a
trusted administrative shell on the deployment host.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
from collections.abc import Sequence

from backend.app.database import dispose_engine, get_session_factory
from backend.app.models import User
from backend.app.repositories.identity import find_user_by_email
from backend.app.services.audit import record_audit_event
from backend.app.services.authentication import hash_password

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or not _EMAIL_PATTERN.fullmatch(email):
        raise argparse.ArgumentTypeError("请输入有效的教师邮箱地址。")
    return email


def validate_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("口令至少需要 12 个字符。")
    if not any(character.isalpha() for character in password):
        raise ValueError("口令至少需要包含一个字母。")
    if not any(character.isdigit() for character in password):
        raise ValueError("口令至少需要包含一个数字。")
    return password


def read_new_password() -> str:
    first = getpass.getpass("输入新口令（不会显示）: ")
    second = getpass.getpass("再次输入新口令（不会显示）: ")
    if first != second:
        raise ValueError("两次输入的口令不一致。")
    return validate_password(first)


def set_account_active(user: User, *, active: bool) -> None:
    """Change account state without allowing pre-deactivation tokens to revive."""
    if user.is_active and not active:
        user.auth_version += 1
    user.is_active = active


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安全管理课堂复盘系统教师账号。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="创建正式教师账号")
    create.add_argument("--email", required=True, type=normalize_email)
    create.add_argument("--display-name", required=True)

    reset = subparsers.add_parser("reset-password", help="重置教师口令")
    reset.add_argument("--email", required=True, type=normalize_email)

    for command in ("activate", "deactivate"):
        account_state = subparsers.add_parser(command, help=f"{command} 教师账号")
        account_state.add_argument("--email", required=True, type=normalize_email)
    return parser


async def apply_command(args: argparse.Namespace, password: str | None) -> str:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        user = await find_user_by_email(session, args.email)
        if args.command == "create":
            if user is not None:
                raise ValueError("该邮箱已经存在；如需换口令，请使用 reset-password。")
            display_name = args.display_name.strip()
            if not display_name or len(display_name) > 128:
                raise ValueError("教师显示名必须为 1 到 128 个字符。")
            if password is None:
                raise ValueError("创建账号需要新口令。")
            user = User(
                email=args.email,
                display_name=display_name,
                password_hash=hash_password(password),
                is_active=True,
            )
            session.add(user)
            await session.flush()
            action = "admin.user.created"
            result = "正式教师账号已创建。"
        else:
            if user is None:
                raise ValueError("没有找到该教师账号。")
            if args.command == "reset-password":
                if password is None:
                    raise ValueError("重置账号需要新口令。")
                user.password_hash = hash_password(password)
                user.auth_version += 1
                action = "admin.user.password_reset"
                result = "教师口令已重置，全部旧登录令牌已撤销。"
            else:
                set_account_active(user, active=args.command == "activate")
                action = f"admin.user.{args.command}d"
                result = "教师账号已启用。" if user.is_active else "教师账号已停用。"

        await record_audit_event(
            session,
            owner_id=user.id,
            actor_service="admin_cli",
            action=action,
            resource_type="user",
            resource_id=user.id,
            details={},
        )
    return result


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = read_new_password() if args.command in {"create", "reset-password"} else None
    try:
        print(await apply_command(args, password))
        return 0
    finally:
        await dispose_engine()


def main() -> int:
    try:
        return asyncio.run(async_main())
    except (ValueError, OSError) as exc:
        print(f"操作未完成：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
