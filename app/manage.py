"""Operational CLI: python -m app.manage create-key NAME"""
import argparse

from app.auth import create_api_key
from app.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app import models  # noqa: F401


def main() -> None:
    """Parse CLI arguments and run the create-key command, printing the new API key once."""
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(dest="cmd", required=True)
    key = sub.add_parser("create-key", help="Issue a new API key")
    key.add_argument("name")
    args = parser.parse_args()

    engine = make_engine(get_settings().database_url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        record, raw = create_api_key(session, args.name)
    print(f"id={record.id} name={record.name}\napi_key={raw}\n(store it now; it cannot be shown again)")


if __name__ == "__main__":
    main()
