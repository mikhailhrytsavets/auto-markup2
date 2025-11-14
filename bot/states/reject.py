from aiogram.fsm.state import State, StatesGroup


class RejectState(StatesGroup):
    waiting_for_comment = State()
    waiting_for_screenshots = State()
    waiting_for_confirmation = State()
