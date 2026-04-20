import re
from markdown import markdown

class WebMarkdownParser:
    @staticmethod
    def normalize(text: str) -> str:
        lines = text.splitlines()
        result = []
        in_code_block = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                result.append(line)
                continue

            if in_code_block:
                result.append(line)
                continue

            line = re.sub(r"^(\s*)[•·]\s+", r"\1- ", line)

            line = re.sub(r"\|\|(.+?)\|\|", r'<span class="spoiler">\1</span>', line)

            line = re.sub(r"__(.+?)__", r"<u>\1</u>", line)

            line = re.sub(r"~~(.+?)~~", r"<del>\1</del>", line)

            line = re.sub(r"<(?!/?[a-zA-Z][^>]*>)", "&lt;", line)

            result.append(line)

        normalized = "\n".join(result)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized

    @staticmethod
    def to_html(text: str) -> str:
        normalized = WebMarkdownParser.normalize(text)
        return markdown(
            normalized,
            extensions=[
                "fenced_code",
                "tables",
                "sane_lists",
                "nl2br",
                "codehilite",
            ],
            extension_configs={
                "codehilite": {
                    "css_class": "highlight",
                    "guess_lang": False,
                }
            },
        )


class TelegramMarkdownV2Parser:
    TELEGRAM_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"

    @staticmethod
    def escape(text: str) -> str:
        parts = TelegramMarkdownV2Parser._split_by_code(text)
        escaped_parts = []

        for part_type, value in parts:
            if part_type in ("code_block", "inline_code"):
                escaped_parts.append(value)
            else:
                escaped_parts.append(TelegramMarkdownV2Parser._escape_non_code(value))

        return "".join(escaped_parts)

    @staticmethod
    def _escape_non_code(text: str) -> str:
        return re.sub(
            r"([\\_*\[\]()~`>#+\-=|{}.!])",
            r"\\\1",
            text,
        )

    @staticmethod
    def _split_by_code(text: str):
        pattern = re.compile(r"(```[\s\S]*?```|`[^`\n]+`)")
        pos = 0
        parts = []

        for match in pattern.finditer(text):
            start, end = match.span()

            if start > pos:
                parts.append(("text", text[pos:start]))

            token = match.group(0)
            if token.startswith("```"):
                parts.append(("code_block", token))
            else:
                parts.append(("inline_code", token))

            pos = end

        if pos < len(text):
            parts.append(("text", text[pos:]))

        return parts

    @staticmethod
    def bold(text: str) -> str:
        return f"*{TelegramMarkdownV2Parser.escape(text)}*"

    @staticmethod
    def italic(text: str) -> str:
        return f"_{TelegramMarkdownV2Parser.escape(text)}_"

    @staticmethod
    def underline(text: str) -> str:
        return f"__{TelegramMarkdownV2Parser.escape(text)}__"

    @staticmethod
    def strikethrough(text: str) -> str:
        return f"~{TelegramMarkdownV2Parser.escape(text)}~"

    @staticmethod
    def spoiler(text: str) -> str:
        return f"||{TelegramMarkdownV2Parser.escape(text)}||"

    @staticmethod
    def inline_code(text: str) -> str:
        safe = text.replace("`", "\\`")
        return f"`{safe}`"

    @staticmethod
    def code_block(text: str, language: str = "") -> str:
        safe = text.replace("```", "\\`\\`\\`")
        return f"```{language}\n{safe}\n```"

    @staticmethod
    def link(label: str, url: str) -> str:
        safe_label = TelegramMarkdownV2Parser.escape(label)
        safe_url = url.replace(")", r"\)")
        return f"[{safe_label}]({safe_url})"
    


class MessageRenderer:
    @staticmethod
    def for_web(text: str) -> str:
        return WebMarkdownParser.to_html(text)

    @staticmethod
    def for_telegram(text: str) -> str:
        return TelegramMarkdownV2Parser.escape(text)
    
