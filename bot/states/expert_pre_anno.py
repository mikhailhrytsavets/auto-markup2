from aiogram.fsm.state import State, StatesGroup


class ExpertPreAnno(StatesGroup):
    waiting_for_conslusion = State()
    waiting_for_confirmation = State()
