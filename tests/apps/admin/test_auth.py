from vashfindir.apps.admin.auth import hash_password, verify_password


def test_verify_password_ok() -> None:
    hashed = hash_password("secret-password")
    assert verify_password("secret-password", hashed) is True


def test_verify_password_wrong() -> None:
    hashed = hash_password("secret-password")
    assert verify_password("other-password", hashed) is False


def test_verify_password_invalid_hash() -> None:
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_verify_password_empty_hash() -> None:
    assert verify_password("x", "") is False
