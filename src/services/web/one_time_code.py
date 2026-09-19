import secrets
import string


CODE_LENGTH = 8
CODE_ALPHABET = string.digits
LOGIN_CODE_TTL = 300
LOGIN_CODE_COOLDOWN = 60
LOGIN_ATTEMPT_WINDOW = 300
LOGIN_ATTEMPT_LIMIT = 10
LOGIN_LINK_TTL = LOGIN_CODE_TTL


def generate_login_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_login_code(code: str) -> str:
    normalized = code.strip()
    if len(normalized) != CODE_LENGTH or not normalized.isdigit():
        raise ValueError("Invalid login code")
    return normalized


def login_code_key(code: str) -> str:
    return f"web_login_code:{code}"


def generate_login_token() -> str:
    return secrets.token_urlsafe(32)


def login_token_key(token: str) -> str:
    return f"web_login_token:{token}"


def login_attempt_key(client_id: str) -> str:
    return f"web_login_attempts:{client_id}"
