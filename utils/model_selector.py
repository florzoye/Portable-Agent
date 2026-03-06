import questionary
from langchain_core.language_models import BaseChatModel
from src.agents.llms.base import BaseLLM


def _model_label(llm: BaseChatModel, wrapper: BaseLLM) -> str:
    model_name = (
        getattr(llm, "model", None)
        or getattr(llm, "model_name", None)
        or type(llm).__name__
    )
    return f"{model_name}  ({type(wrapper).__name__})"


def select_model(
    wrappers: list[BaseLLM],
    llms: list[BaseChatModel],
) -> BaseChatModel:
    if len(llms) == 1:
        return llms[0]

    choices = {
        _model_label(llm, wrapper): llm
        for wrapper, llm in zip(wrappers, llms)
    }

    answer = questionary.select(
        "Выбери модель:",
        choices=list(choices.keys()),
        style=questionary.Style([
            ("selected",    "fg:green bold"),
            ("pointer",     "fg:green bold"),
            ("highlighted", "fg:green"),
            ("question",    "bold"),
            ("answer",      "fg:green bold"),
        ]),
    ).unsafe_ask() 

    if answer is None:
        raise KeyboardInterrupt

    return choices[answer]