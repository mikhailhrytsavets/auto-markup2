from typing import TYPE_CHECKING, Any, cast

from aiogram import Dispatcher, F, Router, types
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.callback_answer import CallbackAnswer
from aiogram.utils.deep_linking import decode_payload
from aiogram.utils.formatting import Bold, Text, as_key_value, as_list, as_marked_section
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka.integrations.aiogram import FromDishka
from loguru import logger
from sqlalchemy.exc import IntegrityError

from bot.states.registration import RegistrationState
from bot.utils.deep_link_codec import DeepLinkCodec
from core.unit_of_work import IUnitOfWork


async def command_start_deep_link(
    msg: types.Message,
    command: CommandObject,
    codec: FromDishka[DeepLinkCodec],
    state: FSMContext,
    uow: FromDishka[IUnitOfWork],
) -> None:
    args = command.args
    if not args:
        await msg.answer("Ошибка")
        return
    try:
        payload = decode_payload(args, decoder=codec.decode)
    except ValueError as e:
        await msg.answer(f"Ошибка: {e}")
        return

    user_type, project_id = payload.split(":")

    if TYPE_CHECKING:
        assert msg.from_user
    async with uow:
        user_exists = await uow.users.exists(tg_id=msg.from_user.id)
    if user_exists:
        await msg.answer(text="Вы уже зарегистрированы")
        return

    await state.update_data(user_type=user_type, project_id=project_id)
    text = as_list(Bold("🔹 Регистрация"), Text("Введите ваше имя"))
    await state.set_state(RegistrationState.waiting_for_name)
    await msg.answer(**text.as_kwargs())


async def name_writen(msg: types.Message, state: FSMContext) -> None:
    name = msg.text
    await state.update_data(name=name)
    text = as_list(Bold("🔹 Регистрация"), Text("Введите ваш логин в CVAT"))
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить", callback_data="skip_cvat")
    await state.set_state(RegistrationState.waiting_for_cvat_login)
    await msg.answer(**text.as_kwargs(), reply_markup=kb.as_markup())


async def cvat_writen(msg: types.Message, state: FSMContext) -> None:
    state_data = await state.update_data(cvat_login=msg.text)
    text = get_confirmation_text(state_data)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="confirm")
    kb.button(text="🔁 Ввести заново", callback_data="reenter")
    await state.set_state(RegistrationState.waiting_for_confirmation)
    await msg.answer(**text.as_kwargs(), reply_markup=kb.adjust(1).as_markup())


async def cvat_skiped(cq: types.CallbackQuery, state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    state_data = await state.update_data(cvat_login="-")
    text = get_confirmation_text(state_data)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="confirm")
    kb.button(text="🔁 Ввести заново", callback_data="reenter")
    reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
    await state.set_state(RegistrationState.waiting_for_confirmation)
    await cq.message.edit_text(**text.as_kwargs(), reply_markup=reply_markup)


def get_confirmation_text(state_data: dict[str, Any]) -> Text:
    text: Text = as_list(
        Bold("🔹 Регистрация"),
        as_marked_section(
            Text("Введённые данные:"),
            as_key_value("Имя", state_data.get("name")),
            as_key_value("CVAT логин", state_data.get("cvat_login")),
            marker="- ",
        ),
    )
    return text


async def confirmed(
    cq: types.CallbackQuery,
    state: FSMContext,
    uow: FromDishka[IUnitOfWork],
    callback_answer: CallbackAnswer,
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    state_data = await state.get_data()
    try:
        async with uow:
            user = uow.users.create(
                {
                    "tg_id": cq.from_user.id,
                    "role": state_data["user_type"],
                    "name": state_data["name"],
                    "cvat_login": state_data["cvat_login"] if state_data["cvat_login"] != "-" else None,
                    "tg_username": cq.from_user.username,
                },
            )
            if state_data["project_id"]:
                project = await uow.projects.get_by_id(int(state_data["project_id"]))
                if not project:
                    callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого проекта", True
                    return
                user.projects.append(project)
            await uow.commit()
    except IntegrityError:
        await cq.message.edit_text("️❗️ Ошибка - пользователь с таким CVAT-логином уже зарегистрирован.")
    else:
        await cq.message.edit_text("✅ Регистрация прошла успешно!")
        logger.info("New user - {}", user)
    finally:
        await state.clear()


async def reenter(cq: types.CallbackQuery, state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    text = as_list(Bold("Регистрация"), Text("Введите ваше имя"))
    await state.set_state(RegistrationState.waiting_for_name)
    await cq.message.edit_text(**text.as_kwargs())


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.message.register(command_start_deep_link, CommandStart(deep_link=True))
    router.message.register(name_writen, F.text, RegistrationState.waiting_for_name)
    router.message.register(cvat_writen, F.text, RegistrationState.waiting_for_cvat_login)
    router.callback_query.register(cvat_skiped, F.data == "skip_cvat", RegistrationState.waiting_for_cvat_login)
    router.callback_query.register(reenter, F.data == "reenter", RegistrationState.waiting_for_confirmation)
    router.callback_query.register(confirmed, F.data == "confirm", RegistrationState.waiting_for_confirmation)
    dp.include_router(router)
