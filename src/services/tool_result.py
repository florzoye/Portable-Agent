from typing import Any


def tool_success(message: str, data: Any = None) -> dict[str, Any]:
    return {
        "ok": True,
        "code": "ok",
        "message": message,
        "data": data,
    }


def tool_failure(code: str, message: str, data: Any = None) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "message": message,
        "data": data,
    }
