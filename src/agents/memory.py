import re


_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def normalize_memory_user_id(user_id: int | str) -> str:
    value = str(user_id).strip()
    if not value or not _USER_ID_PATTERN.fullmatch(value):
        raise ValueError("Invalid memory user ID")
    return value


def user_memory_path(user_id: int | str) -> str:
    return f"/memory/users/{normalize_memory_user_id(user_id)}/AGENTS.md"
