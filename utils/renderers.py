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


class MessageRenderer:
    @staticmethod
    def for_web(text: str) -> str:
        return WebMarkdownParser.to_html(text)