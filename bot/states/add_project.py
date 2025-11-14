from aiogram.fsm.state import State, StatesGroup


class AddProjectState(StatesGroup):
    waiting_for_name = State()
    waiting_for_product = State()
    waiting_for_tg_group_id = State()
