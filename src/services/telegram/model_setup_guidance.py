from dataclasses import dataclass
from enum import StrEnum

from src.services.models.providers import ProviderCapabilities


class ModelSetupIntent(StrEnum):
    LIST_PROVIDERS = "list_providers"
    SHOW_SETUP_HELP = "show_setup_help"
    START_MODEL_SETUP = "start_model_setup"


@dataclass(frozen=True, slots=True)
class ModelSetupRequest:
    intent: ModelSetupIntent
    provider: str | None = None


def detect_model_setup_request(text: str) -> ModelSetupRequest | None:
    normalized = " ".join(text.casefold().split())
    if not normalized:
        return None
    if any(marker in normalized for marker in ("какие провайдеры", "список провайдеров", "доступные провайдеры")):
        return ModelSetupRequest(ModelSetupIntent.LIST_PROVIDERS)
    if any(marker in normalized for marker in ("настроить модель", "добавить модель", "подключить модель")):
        provider = next(
            (
                candidate
                for candidate in ("openai", "xai", "ollama")
                if candidate in normalized
            ),
            None,
        )
        return ModelSetupRequest(ModelSetupIntent.START_MODEL_SETUP, provider)
    if any(marker in normalized for marker in ("помощь с модель", "как добавить модель", "настройка модели")):
        return ModelSetupRequest(ModelSetupIntent.SHOW_SETUP_HELP)
    return None


def format_provider_help(capabilities: tuple[ProviderCapabilities, ...]) -> str:
    lines = ["Доступные провайдеры:"]
    for capability in capabilities:
        ownership = (
            "ключ пользователя"
            if capability.requires_user_api_key
            else "бесплатный managed-провайдер"
        )
        lines.append(f"• {capability.display_name}: {ownership}")
    return "\n".join(lines)


def setup_help_text() -> str:
    return (
        "Настройка модели проходит в два шага: выберите провайдера, "
        "затем укажите имя модели. Для OpenAI и xAI потребуется API-ключ. "
        "Ключ вводится отдельным сообщением, не показывается обратно и "
        "сохраняется зашифрованным."
    )
