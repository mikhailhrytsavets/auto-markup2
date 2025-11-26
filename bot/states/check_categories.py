from aiogram.fsm.state import State, StatesGroup


class CheckCategoriesView(StatesGroup):
    from_default_approve = State()
    from_expert_annotate = State()
    from_approve_with_self_anno = State()
