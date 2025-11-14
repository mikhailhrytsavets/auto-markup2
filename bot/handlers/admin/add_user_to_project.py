from typing import TYPE_CHECKING

from aiogram import Dispatcher, F, Router, exceptions, types
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.utils.callback_answer import CallbackAnswer
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka.integrations.aiogram import FromDishka

from bot.states.add_user_to_project import AddProjectUserState
from core.models.user import UserRoleEnum
from core.unit_of_work import IUnitOfWork


class Project(CallbackData, prefix="for-project"):
    project_id: int


async def add_user_to_project(msg: types.Message, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    if TYPE_CHECKING:
        assert msg.from_user
    async with uow:
        user = await uow.users.get_by_id(msg.from_user.id)
        if not user or user.role != UserRoleEnum.ADMIN:
            return
    await state.set_state(AddProjectUserState.waiting_for_user)
    await msg.answer(text="Пришлите TG-id пользователя")


async def user_tg_id_writen(msg: types.Message, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    if TYPE_CHECKING:
        assert msg.text
        assert msg.bot

    user_tg_id = msg.text
    try:
        await msg.bot.get_chat(chat_id=user_tg_id)
    except exceptions.TelegramBadRequest:
        await state.clear()
        await msg.answer("Пользователь не найден")
        return
    await state.update_data(validator_tg_id=user_tg_id)
    await state.set_state(AddProjectUserState.waiting_for_project)

    kb = InlineKeyboardBuilder()
    async with uow:
        projects = await uow.projects.get_all_without_user(user_id=int(user_tg_id))
        for project in projects:
            kb.button(text=project.name, callback_data=Project(project_id=project.id))
    reply_markup = kb.adjust(1).as_markup()
    await msg.answer(text="Выберите проект", reply_markup=reply_markup)


async def project_choosen(
    cq: types.CallbackQuery,
    callback_data: Project,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    state: FSMContext,
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)

    state_data = await state.get_data()

    async with uow:
        user = await uow.users.get_by_tg_id_with_projects(int(state_data["validator_tg_id"]))
        if not user:
            callback_answer.text = "Валидатор не найден"
            return
        project = await uow.projects.get_by_id(callback_data.project_id)
        if not project:
            callback_answer.text = "Проект не найден"
            return
        user.projects.append(project)
        await uow.commit()

    await state.clear()
    await cq.message.edit_text(text="✅ Пользователь добавлен в проект")


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.message.register(add_user_to_project, Command("user_project"))
    router.message.register(user_tg_id_writen, F.text, AddProjectUserState.waiting_for_user)
    router.callback_query.register(project_choosen, Project.filter(), AddProjectUserState.waiting_for_project)
    dp.include_router(router)
