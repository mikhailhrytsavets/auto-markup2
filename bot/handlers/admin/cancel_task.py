from typing import TYPE_CHECKING

from aiogram import Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka.integrations.aiogram import FromDishka

from bot.states.cancel_task import CancelTask
from core.models.study import StudyStatusEnum
from core.models.user import UserRoleEnum
from core.unit_of_work import IUnitOfWork


async def cancel_task(msg: types.Message, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    if TYPE_CHECKING:
        assert msg.from_user
    async with uow:
        user = await uow.users.get_by_id(msg.from_user.id)
        if not user or user.role != UserRoleEnum.ADMIN:
            return
    await state.set_state(CancelTask.waiting_for_study_iuid)
    await msg.answer(text="Напишите study_iuid")


async def study_iuid_writen(msg: types.Message, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    if TYPE_CHECKING:
        assert msg.text
    study_iuid = msg.text
    not_found = False
    study_status = StudyStatusEnum.ASSIGNED
    study_id = None
    async with uow:
        study = await uow.studies.get_by_iuid(study_iuid)
        if not study:
            not_found = True
        else:
            study_status = study.status
            study_id = study.id
    if not_found:
        await state.clear()
        await msg.reply("❗️ Такого исследования нет в базе")
        return
    if study_status.value.startswith("closed") or study_status == StudyStatusEnum.APPROVED:
        await state.clear()
        await msg.reply("❗️ Это исследование уже закрыто")
        return
    if study_status == StudyStatusEnum.NEW:
        await state.clear()
        await msg.reply("❗️ Это исследование еще никто не взял в работу")
        return
    await state.update_data(study_id=study_id)
    await state.set_state(CancelTask.waiting_for_confirmation)
    kb = InlineKeyboardBuilder()
    kb.button(text="Да", callback_data="yes")
    kb.button(text="Нет", callback_data="no")
    reply_markup = kb.adjust(1).as_markup()
    await msg.answer(text="🔹 Вы точно желаете обнулить исследование?", reply_markup=reply_markup)


async def confirmed(cq: types.CallbackQuery, state: FSMContext, uow: FromDishka[IUnitOfWork]) -> None:
    study_id = await state.get_value("study_id")
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
        assert study_id

    async with uow:
        await uow.studies.update(
            study_id,
            {
                "status": StudyStatusEnum.NEW,
                "iteration_count": 0,
                "annotator_id": None,
                "expert_id": None,
                "nc_share_link": None,
                "nc_upload_link": None,
            },
        )
        await uow.commit()
    await state.clear()
    await cq.message.edit_text(text="✅ Исследование успешно сброшено")


async def cancel(cq: types.CallbackQuery, state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    await state.clear()
    await cq.message.edit_text(text=cq.message.html_text + "\n\nОтменено")


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.message.register(cancel_task, Command("cancel_task"))
    router.message.register(study_iuid_writen, F.text, CancelTask.waiting_for_study_iuid)
    router.callback_query.register(confirmed, F.data == "yes", CancelTask.waiting_for_confirmation)
    router.callback_query.register(cancel, F.data == "no", CancelTask.waiting_for_confirmation)
    dp.include_router(router)
