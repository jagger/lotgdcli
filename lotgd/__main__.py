import argparse
import os

from .client import DEFAULT_URL, Client
from .repl import Repl


def main():
    ap = argparse.ArgumentParser(prog="lotgd", description="Terminal client for Legend of the Green Dragon")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"server base URL (default {DEFAULT_URL})")
    ap.add_argument("--user", "-u", help="character name to log in as (omit to browse logged out)")
    ap.add_argument("--debug", metavar="DIR", nargs="?", const="debug",
                    help="log requests and save every page's HTML to DIR (default ./debug)")
    args = ap.parse_args()
    Repl(Client(args.url, args.debug), args.user, os.environ.get("LOTGD_PASSWORD")).run()


if __name__ == "__main__":
    main()
