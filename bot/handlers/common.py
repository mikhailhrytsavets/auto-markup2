from aiogram import Dispatcher, Router, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from dishka.integrations.aiogram import FromDishka

from core.models.user import UserRoleEnum
from core.unit_of_work import IUnitOfWork


async def command_start(msg: types.Message, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    await state.clear()
    if not msg.from_user:
        return
    send_command = False
    async with uow:
        user = await uow.users.get_by_id(msg.from_user.id)
        if user and user.role == UserRoleEnum.ANNOTATOR:
            send_command = True
    if send_command:
        await msg.answer(text="/task - получить задание на разметку")


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.message.register(command_start, CommandStart(), StateFilter("*"))
    dp.include_router(router)
