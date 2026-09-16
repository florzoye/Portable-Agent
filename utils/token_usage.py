from collections.abc import Mapping
from typing import Any


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def extract_token_usage(chunk: Any) -> dict[str, int | str | None]:
    usage = _mapping(getattr(chunk, "usage_metadata", None))
    metadata = _mapping(getattr(chunk, "response_metadata", None))
    response_metadata = _mapping(metadata.get("usage"))

    input_tokens = int(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or response_metadata.get("input_tokens")
        or response_metadata.get("prompt_tokens")
        or 0
    )
    output_tokens = int(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or response_metadata.get("output_tokens")
        or response_metadata.get("completion_tokens")
        or 0
    )
    total_tokens = int(
        usage.get("total_tokens")
        or response_metadata.get("total_tokens")
        or input_tokens + output_tokens
    )
    model = (
        metadata.get("model_name")
        or metadata.get("model")
        or getattr(chunk, "model_name", None)
    )
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
