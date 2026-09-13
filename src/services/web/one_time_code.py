import secrets
import string


CODE_LENGTH = 8
CODE_ALPHABET = string.digits


def generate_login_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_login_code(code: str) -> str:
    normalized = code.strip()
    if len(normalized) != CODE_LENGTH or not normalized.isdigit():
        raise ValueError("Invalid login code")
    return normalized
