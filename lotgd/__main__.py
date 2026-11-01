import argparse
import os
import sys

from .client import DEFAULT_URL, Client
from .credentials import load_credentials
from .repl import Repl


def main():
    ap = argparse.ArgumentParser(prog="lotgd", description="Terminal client for Legend of the Green Dragon")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"server base URL (default {DEFAULT_URL})")
    ap.add_argument("--user", "-u", help="character name to log in as (omit to browse logged out)")
    ap.add_argument("--login", "-l", action="store_true",
                    help="log in as LOTGD_USER or the credentials file's user when -u isn't given")
    ap.add_argument("--debug", metavar="DIR", nargs="?", const="debug",
                    help="log requests and save every page's HTML to DIR (default ./debug)")
    args = ap.parse_args()
    if args.user or args.login:
        user, password = load_credentials(args.user)
        login = True
    else:  # browse logged out, unless a password in the environment asks to log in
        user, password = None, os.environ.get("LOTGD_PASSWORD")
        login = bool(password)
    sys.exit(Repl(Client(args.url, args.debug), user, password, login=login).run())


if __name__ == "__main__":
    main()
