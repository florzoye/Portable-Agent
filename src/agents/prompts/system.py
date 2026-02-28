from langchain_core.messages import SystemMessage

SYSTEM_PROMPT_TEMPLATE = (
    "You are a personal assistant with access to Google Calendar tools.\n\n"
    "STRICT RULES:\n"
    "- When asked to send something to Telegram, you MUST call send_tg_message tool.\n"
    "- Never claim you sent something without actually calling the tool first.\n"
    "- Confirm actions only AFTER the tool returns success.\n"
    "- Always respond in the same language the user writes in.\n"
)


class AgentSystemPrompt:
    @staticmethod
    def get_prompt(memory_path: str | None = None, tg_id: int | str | None = None) -> SystemMessage:
        content = SYSTEM_PROMPT_TEMPLATE
        if tg_id is not None:
            content += f"\nCurrent user Telegram ID: {tg_id}\n"
        if memory_path is not None:
            content += (
                f"\nYour memory file is located at: {memory_path}\n"
                "Always save important information to this exact path.\n"
            )
        return SystemMessage(content=content)