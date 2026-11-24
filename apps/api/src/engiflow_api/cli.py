"""Linha de comando: criação do usuário único. A senha é lida sem eco, nunca por argumento."""

import argparse
import getpass
import sys

from engiflow_api.application.auth import create_user
from engiflow_api.core.config import get_settings
from engiflow_api.infrastructure.db import build_engine, build_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engiflow-api")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user", help="cria o único usuário (falha se já existir)")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    if args.command == "create-user":
        password = getpass.getpass("Senha (mínimo 12 caracteres): ")
        if password != getpass.getpass("Repita a senha: "):
            print("As senhas não conferem.", file=sys.stderr)
            return 1
        factory = build_session_factory(build_engine(get_settings().database_url))
        with factory() as db:
            try:
                create_user(db, email=args.email, display_name=args.name, password=password)
                db.commit()
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        print("Usuário criado.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
