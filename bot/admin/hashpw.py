import sys
from getpass import getpass

from bot.admin.auth import hash_password


def read_password() -> str:
    """Password from argv, stdin (piped), or interactive prompt."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return getpass("Пароль: ")


def main() -> None:
    password = read_password()
    if not password:
        raise SystemExit("Пароль не может быть пустым.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
