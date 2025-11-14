from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_cvat_login = State()
    waiting_for_confirmation = State()
