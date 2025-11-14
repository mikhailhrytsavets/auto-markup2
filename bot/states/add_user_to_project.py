from aiogram.fsm.state import State, StatesGroup


class AddProjectUserState(StatesGroup):
    waiting_for_user = State()
    waiting_for_project = State()
