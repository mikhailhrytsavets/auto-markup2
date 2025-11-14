from aiogram.fsm.state import State, StatesGroup


class CancelTask(StatesGroup):
    waiting_for_study_iuid = State()
    waiting_for_confirmation = State()
