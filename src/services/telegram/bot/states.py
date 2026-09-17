from aiogram.fsm.state import State, StatesGroup


class TelegramMode(StatesGroup):
    navigation = State()
    chat = State()
