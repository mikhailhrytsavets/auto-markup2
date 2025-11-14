from typing import TYPE_CHECKING, cast

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.deep_linking import create_start_link
from aiogram.utils.formatting import Bold, Code, as_line, as_list
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka.integrations.aiogram import FromDishka
from loguru import logger

from bot.utils.deep_link_codec import DeepLinkCodec
from core.models.user import UserRoleEnum
from core.unit_of_work import IUnitOfWork


class LinkFor(CallbackData, prefix="link-user-type"):
    user_type: UserRoleEnum


class GenRegLinkCallback(CallbackData, prefix="link-project"):
    user_type: UserRoleEnum
    project_id: int


async def generate_registraition_link_choose_user_type(msg: types.Message, uow: FromDishka[IUnitOfWork]) -> None:
    if TYPE_CHECKING:
        assert msg.from_user
    async with uow:
        user = await uow.users.get_by_id(msg.from_user.id)
        if not user or user.role != UserRoleEnum.ADMIN:
            return
    kb = InlineKeyboardBuilder()
    kb.button(text="Разметчик", callback_data=LinkFor(user_type=UserRoleEnum.ANNOTATOR))
    kb.button(text="Эксперт", callback_data=LinkFor(user_type=UserRoleEnum.VALIDATOR))
    kb.button(text="Администратор", callback_data=LinkFor(user_type=UserRoleEnum.ADMIN))
    await msg.answer(text="🔹 Выберите тип пользователя", reply_markup=kb.adjust(1).as_markup())


async def generate_registraition_link_choose_project(
    cq: types.CallbackQuery,
    callback_data: LinkFor,
    codec: FromDishka[DeepLinkCodec],
    uow: FromDishka[IUnitOfWork],
) -> None:
    if TYPE_CHECKING:
        assert cq.bot
        assert isinstance(cq.message, types.Message)
    if callback_data.user_type == UserRoleEnum.ANNOTATOR:
        kb = InlineKeyboardBuilder()
        async with uow:
            projects = await uow.projects.get_all()
            for project in projects:
                kb.button(
                    text=project.name,
                    callback_data=GenRegLinkCallback(user_type=callback_data.user_type, project_id=project.id),
                )
        reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
        await cq.message.edit_text(text="🔹 Выберите проект", reply_markup=reply_markup)
    else:
        link = await create_start_link(
            cq.bot,
            payload=f"{callback_data.user_type.name}:",
            encode=True,
            encoder=codec.encode,
        )
        text = as_list(
            Bold("🔹 Ссылка на регистрацию:"),
            as_line(Bold("Тип пользователя: "), callback_data.user_type.name),
            Code(link),
        )
        await cq.message.edit_text(**text.as_kwargs())
        logger.info("Reg link generated for {}", callback_data.user_type.name)


async def generate_registration_link(
    cq: types.CallbackQuery,
    callback_data: GenRegLinkCallback,
    bot: Bot,
    codec: FromDishka[DeepLinkCodec],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    link = await create_start_link(
        bot,
        payload=f"{callback_data.user_type.name}:{callback_data.project_id}",
        encode=True,
        encoder=codec.encode,
    )
    text = as_list(
        Bold("🔹 Ссылка на регистрацию:"),
        as_line(Bold("Тип пользователя: "), callback_data.user_type.name),
        Code(link),
    )
    await cq.message.edit_text(**text.as_kwargs())
    logger.info("Reg link generated for {}", callback_data.user_type.name)


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.message.register(generate_registraition_link_choose_user_type, Command("gen_reg_link"))
    router.callback_query.register(generate_registraition_link_choose_project, LinkFor.filter())
    router.callback_query.register(generate_registration_link, GenRegLinkCallback.filter())
    dp.include_router(router)
