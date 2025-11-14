from typing import TYPE_CHECKING

from aiogram import Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.utils.formatting import Bold, Italic, Text, as_list
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka.integrations.aiogram import FromDishka
from loguru import logger
from sqlalchemy.exc import IntegrityError

from bot.states.add_project import AddProjectState
from core.models.project import ProductEnum
from core.models.user import UserRoleEnum
from core.unit_of_work import IUnitOfWork


class Product(CallbackData, prefix="product"):
    product: ProductEnum


async def add_project(msg: types.Message, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    if TYPE_CHECKING:
        assert msg.from_user
    async with uow:
        user = await uow.users.get_by_id(msg.from_user.id)
        if not user or user.role != UserRoleEnum.ADMIN:
            return
    await state.set_state(AddProjectState.waiting_for_name)
    await msg.answer(text="Напишите название проекта")


async def project_name_writen(msg: types.Message, state: FSMContext) -> None:
    project_name = msg.text
    await state.update_data(project_name=project_name)
    await state.set_state(AddProjectState.waiting_for_product)
    text = as_list(
        Bold("Добавление проекта"),
        Text("Выберите продукт"),
    )
    kb = InlineKeyboardBuilder()
    for product in ProductEnum:
        kb.button(text=product.name, callback_data=Product(product=product))
    reply_markup = kb.adjust(2).as_markup()
    await msg.answer(**text.as_kwargs(), reply_markup=reply_markup)


async def product_chosen(cq: types.CallbackQuery, callback_data: Product, state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    await state.update_data(product=callback_data.product.value)
    await state.set_state(AddProjectState.waiting_for_tg_group_id)
    text = as_list(
        Bold("Добавление проекта"),
        Text("❗️ Бот должен быть добавлен в канал в качестве администратора и иметь права на управление сообщениями."),
        Text("Пришлите TG-id канала проекта"),
        Italic("Например: -1003107200430"),
    )
    await cq.message.edit_text(**text.as_kwargs())


async def tg_channel_writen(msg: types.Message, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    if TYPE_CHECKING:
        assert msg.bot
    chat_id = msg.text
    if not chat_id or not chat_id.startswith("-100"):
        await msg.answer("❗️ Ошибка - некорректный ID")
        return

    chat_member = await msg.bot.get_chat_member(chat_id=chat_id, user_id=msg.bot.id)
    if not isinstance(chat_member, types.ChatMemberAdministrator) or not all(
        (chat_member.can_delete_messages, chat_member.can_edit_messages, chat_member.can_post_messages),
    ):
        text = as_list(
            Bold("Добавление проекта"),
            Text(
                "❗️ Бот должен быть добавлен в канал в качестве "
                "администратора и иметь права на управление сообщениями.",
            ),
            Italic("Реализуйте эти требования и пришлите TG-id еще раз."),
        )
        await msg.answer(**text.as_kwargs())
        return

    state_data = await state.get_data()
    try:
        async with uow:
            project = uow.projects.create(
                {
                    "name": state_data["project_name"],
                    "tg_group_id": int(chat_id),
                    "product": ProductEnum(state_data["product"]),
                },
            )
            await uow.commit()
    except IntegrityError:
        await msg.answer("❗️ Ошибка - проект с таким именем или каналом уже создан.")
    else:
        await msg.answer("✅ Проект успешно добавлен!")
        logger.info("New project - {}", project)
    finally:
        await state.clear()


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.message.register(add_project, Command("add_project"))
    router.message.register(project_name_writen, F.text, AddProjectState.waiting_for_name)
    router.callback_query.register(product_chosen, Product.filter(), AddProjectState.waiting_for_product)
    router.message.register(tg_channel_writen, F.text, AddProjectState.waiting_for_tg_group_id)
    dp.include_router(router)
