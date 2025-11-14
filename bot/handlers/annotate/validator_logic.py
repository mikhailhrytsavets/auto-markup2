import asyncio
from typing import TYPE_CHECKING, cast

from aiogram import Dispatcher, F, Router, types
from aiogram.filters import or_f
from aiogram.fsm.context import FSMContext
from aiogram.utils.callback_answer import CallbackAnswer
from aiogram.utils.formatting import Bold, Code, Text, TextLink, Url, as_line, as_list
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.media_group import MediaGroupBuilder
from dishka.integrations.aiogram import FromDishka
from loguru import logger

from bot.handlers.annotate.utils import (
    AnnoReview,
    ApproveAnno,
    ApproveWithSelfAnno,
    CloseAnno,
    CloseAnnoReason,
    ConfirmApproveAnno,
    ExpertAnno,
    ExpertCloseAnno,
    ExpertReworkReview,
    PreExpertAnno,
    ReAnnoStudy,
    RejectAnno,
    ReportReasons,
    StudyAnnoReview,
    StudyReportReview,
    get_assigned_study_text,
)
from bot.middleware.album_middleware import MediaGroupMiddleware
from bot.states.expert_pre_anno import ExpertPreAnno
from bot.states.reject import RejectState
from core.config import Settings
from core.models.study import Study, StudyStatusEnum
from core.unit_of_work import IUnitOfWork
from core.utils.nextcloud import NextcloudUtils

async_lock = asyncio.Lock()


async def annotate_review(
    cq: types.CallbackQuery,
    callback_data: StudyAnnoReview,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    settings: FromDishka[Settings],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
        assert cq.bot

    study_id = callback_data.study_id
    user_tg_id = cq.from_user.id
    async with async_lock, uow:
        study = await uow.studies.get_by_id(study_id)
        if not study:
            logger.error("Study with id={} is not found", study_id)
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return

        if study.expert_id:
            callback_answer.text, callback_answer.show_alert = "Задача уже назначена другому эксперту", True
            return

        if await uow.studies.get_in_review_for_expert(cq.from_user.id):
            callback_answer.text, callback_answer.show_alert = "У ваc есть незавершенные проверки", True
            return

        user = await uow.users.get_by_id(user_tg_id)
        if not user:
            callback_answer.text, callback_answer.show_alert = "Вы не зарегистрированы в боте!", True
            return

        study.expert_id = user_tg_id
        study.status = StudyStatusEnum.IN_REVIEW
        await uow.commit()
        expert_data = as_line(
            Text("\n\nВзял в работу - "),
            as_line(
                TextLink(user.name, url=f"tg://user?id={user.tg_id}"),
                Text(f" (@{user.tg_username})") if user.tg_username else Text(),
            ),
        )
    text = cq.message.html_text + expert_data.as_html()
    await cq.message.edit_text(text=text)
    callback_answer.text = "Вам назначена задача ✅"

    review_text = get_anno_review_text(study)
    kb = get_anno_review_kb(study, iteration_limit=settings.ITERATION_LIMIT)
    await cq.bot.send_message(
        chat_id=user_tg_id,
        **review_text.as_kwargs(),
        reply_markup=kb,
        reply_parameters=types.ReplyParameters(
            message_id=cq.message.message_id,
            chat_id=cq.message.chat.id,
        ),
    )
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("Expert picked up study for validation")


def get_anno_review_text(study: Study) -> Text:
    text: Text = as_list(
        Bold("🔹 Проверка разметки") if study.iteration_count == 1 else Bold("🔺 Перепроверка разметки"),
        as_line(Bold("StudyIUID: "), Code(study.study_iuid)),
        as_line(Bold("Номер папки: "), Code(study.study_path.rsplit("/", maxsplit=1)[1])),
        as_line(Bold("Номер итерации: "), Text(study.iteration_count)),
        as_line(Bold("Исходное КТ: "), Url(study.nc_share_link)),
        as_line(Bold("Разметка: "), Url(study.nc_upload_link)),
    )
    return text


def get_anno_review_kb(study: Study, *, iteration_limit: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=ApproveAnno(study_id=study.id))
    if study.iteration_count != iteration_limit:
        kb.button(text="💢 Отклонить", callback_data=RejectAnno(study_id=study.id))
    else:
        kb.button(text="📝 Разметить самому", callback_data=PreExpertAnno(study_id=study.id))
    kb.button(text="Закрыть", callback_data=CloseAnno(study_id=study.id))
    return cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())


async def annotate_review_view_only(
    cq: types.CallbackQuery,
    callback_data: StudyAnnoReview,
    callback_answer: CallbackAnswer,
    state: FSMContext,
    uow: FromDishka[IUnitOfWork],
    settings: FromDishka[Settings],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    await state.clear()
    async with uow:
        study = await uow.studies.get_by_id(callback_data.study_id)
        if not study:
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return
        text = get_anno_review_text(study)
        kb = get_anno_review_kb(study, iteration_limit=settings.ITERATION_LIMIT)
    await cq.message.edit_text(
        **text.as_kwargs(),
        reply_markup=kb,
    )


async def rework_review_start(
    cq: types.CallbackQuery,
    callback_data: ExpertReworkReview,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    settings: FromDishka[Settings],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
        assert cq.message.reply_to_message

    async with uow:
        study = await uow.studies.update(
            callback_data.study_id,
            {
                "status": StudyStatusEnum.IN_REVIEW,
            },
        )
        if not study:
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return
        await uow.commit()

    text = get_anno_review_text(study)
    kb = get_anno_review_kb(study, iteration_limit=settings.ITERATION_LIMIT)
    await cq.message.answer(
        **text.as_kwargs(),
        reply_markup=kb,
        reply_to_message_id=cq.message.reply_to_message.message_id,
    )

    await cq.message.delete()


async def approve_anno(cq: types.CallbackQuery, callback_data: StudyAnnoReview) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    kb = InlineKeyboardBuilder()
    kb.button(text="Да", callback_data=ConfirmApproveAnno(study_id=callback_data.study_id))
    kb.button(text="Да, но с доразметкой", callback_data=ApproveWithSelfAnno(study_id=callback_data.study_id))
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=callback_data.study_id))
    reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
    await cq.message.edit_text(text="Вы точно желаете подтвердить корректность разметки?", reply_markup=reply_markup)


async def approve_anno_confirmed(
    cq: types.CallbackQuery,
    callback_data: StudyAnnoReview,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
        assert cq.bot

    study_iuid = callback_data.study_id
    async with uow:
        study = await uow.studies.update(
            study_iuid,
            {
                "status": StudyStatusEnum.APPROVED,
            },
        )
        if not study:
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return
        if not study.annotator_id:
            callback_answer.text, callback_answer.show_alert = "Ошибка - у разметки нет разметчика", True
            return
        expert = await uow.users.get_by_id(cq.from_user.id)
        if not expert:
            callback_answer.text, callback_answer.show_alert = "Вы не зарегистрированы в боте!", True
            return
        await uow.commit()

    text = as_list(
        get_anno_review_text(study),
        Text("Одобрено ✅"),
        sep="\n\n",
    )
    await cq.message.edit_text(**text.as_kwargs())
    text = as_line(
        Text("✅ Эксперт "),
        as_line(
            TextLink(expert.name, url=f"tg://user?id={expert.tg_id}"),
            Text(f" (@{expert.tg_username})") if expert.tg_username else Text(),
            end="",
        ),
        Text(" одобрил разметку исследования - "),
        Code(study.study_iuid),
    )
    await cq.bot.send_message(
        chat_id=study.annotator_id,
        **text.as_kwargs(),
    )
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("Expert approved the annotation")

    upload_path = study.study_path.replace("1-original-data", "2-check")
    latest_upload = f"{upload_path}/version_{study.iteration_count}"
    dst_path = upload_path.replace("2-check", "3-research")
    await nc_util.copy_directory(src_dir=latest_upload, dst_dir=dst_path)
    with logger.contextualize(study_iuid=study.study_iuid, iteration_count=study.iteration_count):
        logger.info("The latest annotation version was copied to the 3-research directory")


async def close_anno(cq: types.CallbackQuery, callback_data: StudyAnnoReview) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Normal",
        callback_data=CloseAnnoReason(study_id=callback_data.study_id, reason=ReportReasons.NORMAL),
    )
    kb.button(
        text="Incorrect",
        callback_data=CloseAnnoReason(study_id=callback_data.study_id, reason=ReportReasons.INCORRECT),
    )
    kb.button(
        text="Other",
        callback_data=CloseAnnoReason(study_id=callback_data.study_id, reason=ReportReasons.OTHER_PATHOLOGY),
    )
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=callback_data.study_id))
    reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
    await cq.message.edit_text(text="Выберите причину закрытия", reply_markup=reply_markup)


async def close_anno_reason_choosen(
    cq: types.CallbackQuery,
    callback_data: CloseAnnoReason,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
        assert cq.bot

    match callback_data.reason:
        case ReportReasons.NORMAL:
            status = StudyStatusEnum.CLOSED_N
        case ReportReasons.INCORRECT:
            status = StudyStatusEnum.CLOSED_I
        case ReportReasons.OTHER_PATHOLOGY:
            status = StudyStatusEnum.CLOSED_OP

    study_iuid = callback_data.study_id
    async with uow:
        study = await uow.studies.update(
            study_iuid,
            {
                "status": status,
            },
        )
        if not study:
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return
        if not study.annotator_id:
            callback_answer.text, callback_answer.show_alert = "Ошибка - у разметки нет разметчика", True
            return
        await uow.commit()
        expert = await uow.users.get_by_id(cq.from_user.id)
        if not expert:
            callback_answer.text, callback_answer.show_alert = "Вы не зарегистрированы в боте!", True
            return
        expert_data = as_line(
            TextLink(expert.name, url=f"tg://user?id={expert.tg_id}"),
            Text(f" (@{expert.tg_username})") if expert.tg_username else Text(),
        )

    text = as_list(
        get_anno_review_text(study),
        Text(f"Закрыто по причине - {callback_data.reason.name} ✅"),
        sep="\n\n",
    )
    await cq.message.edit_text(**text.as_kwargs())
    text = as_line(
        Text("❗️ Эксперт "),
        expert_data,
        Text(" закрыл разметку исследования: "),
        Code(study.study_iuid),
        Text(f"\nПричина: {callback_data.reason.name}"),
    )
    await cq.bot.send_message(
        chat_id=study.annotator_id,
        **text.as_kwargs(),
    )
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
        reason=callback_data.reason.name,
    ):
        logger.info("Expert closed the study annotation")


async def reject_annotate(cq: types.CallbackQuery, callback_data: StudyAnnoReview, state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    await state.set_state(RejectState.waiting_for_comment)
    await state.update_data(study_id=callback_data.study_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=callback_data.study_id))
    reply_markup = kb.as_markup()
    await cq.message.edit_text(text="Напишите комментарий", reply_markup=reply_markup)


async def reject_comment_writen(msg: types.Message, state: FSMContext) -> None:
    state_data = await state.update_data(comment=msg.text, photo_ids=[], reject_comment_msg_id=msg.message_id)
    await state.set_state(RejectState.waiting_for_screenshots)
    text = "Пришлите скриншот"
    kb = InlineKeyboardBuilder()
    kb.button(text="Отправить без скриншота", callback_data="send")
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=state_data["study_id"]))
    reply_markup = kb.adjust(1).as_markup()
    await msg.answer(text=text, reply_markup=reply_markup)


async def reject_new_photo(msg: types.Message, state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert msg.photo
    state_data = await state.get_data()
    photo_ids = state_data["photo_ids"]
    if len(photo_ids) < 10:
        photo_ids.append(msg.photo[-1].file_id)
        await state.update_data(photo_ids=photo_ids)
        text = "Пришлите еще изображение или нажмите на кнопку"
    else:
        text = "Максимум 10 изображений, больше добавить нельзя"

    mg = MediaGroupBuilder(caption=state_data["comment"])
    for photo_id in photo_ids:
        mg.add_photo(media=photo_id)
    msgs = await msg.answer_media_group(media=mg.build())

    reject_comment_msg_id = msgs[0].message_id
    await state.update_data(reject_comment_msg_id=reject_comment_msg_id)

    kb = InlineKeyboardBuilder()
    kb.button(text="Отправить", callback_data="send")
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=state_data["study_id"]))
    await msg.answer(text=text, reply_markup=kb.adjust(1).as_markup())


async def reject_new_photos(msg: types.Message, album: list[types.Message], state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert msg.photo

    state_data = await state.get_data()
    photo_ids = state_data["photo_ids"]
    if len(photo_ids) < 10:
        await state.update_data(photo_ids=photo_ids)
        text = "Пришлите еще изображение или нажмите на кнопку"
        for element in album:
            if element.photo:
                photo_ids.append(msg.photo[-1].file_id)
            else:
                await msg.reply("Поддeрживаются только изображения!")
                return
            if len(photo_ids) == 10:
                break
        await state.update_data(photo_ids=photo_ids)
    else:
        text = "Максимум 10 изображений, больше добавить нельзя"

    mg = MediaGroupBuilder(caption=state_data["comment"])
    for photo_id in photo_ids:
        mg.add_photo(media=photo_id)
    msgs = await msg.answer_media_group(media=mg.build())

    reject_comment_msg_id = msgs[0].message_id
    await state.update_data(reject_comment_msg_id=reject_comment_msg_id)

    kb = InlineKeyboardBuilder()
    kb.button(text="Отправить", callback_data="send")
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=state_data["study_id"]))
    await msg.answer(text=text, reply_markup=kb.adjust(1).as_markup())


async def send_reject(
    cq: types.CallbackQuery,
    callback_answer: CallbackAnswer,
    state: FSMContext,
    uow: FromDishka[IUnitOfWork],
) -> None:
    if TYPE_CHECKING:
        assert cq.bot
        assert isinstance(cq.message, types.Message)

    state_data = await state.get_data()
    study_id = state_data["study_id"]
    async with uow:
        study = await uow.studies.update(
            study_id,
            {
                "status": StudyStatusEnum.WAITING_REWORK,
                "reject_comment_msg_id": state_data["reject_comment_msg_id"],
            },
        )
        if not study:
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return
        if not study.annotator_id:
            callback_answer.text, callback_answer.show_alert = "Ошибка - у разметки нет разметчика", True
            return
        await uow.commit()
        expert = await uow.users.get_by_id(cq.from_user.id)
        if not expert:
            callback_answer.text, callback_answer.show_alert = "Вы не зарегистрированы в боте!", True
            return
        expert_data = as_line(
            TextLink(expert.name, url=f"tg://user?id={expert.tg_id}"),
            Text(f" (@{expert.tg_username})") if expert.tg_username else Text(),
        )

    text = as_line(
        Text("❗️ Эксперт "),
        expert_data,
        Text(" запросил доразметку исследования: "),
        Code(study.study_iuid),
        Text("\n\nКомментарий в сообщении ниже"),
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="Взять в работу", callback_data=ReAnnoStudy(study_id=study_id))
    reply_markup = kb.adjust(1).as_markup()
    await cq.bot.send_message(
        chat_id=study.annotator_id,
        **text.as_kwargs(),
        reply_markup=reply_markup,
    )
    if state_data.get("photo_ids"):
        mg = MediaGroupBuilder(caption=state_data["comment"])
        for photo_id in state_data["photo_ids"]:
            mg.add_photo(media=photo_id)
        await cq.bot.send_media_group(
            chat_id=study.annotator_id,
            media=mg.build(),
        )
    else:
        await cq.bot.send_message(
            chat_id=study.annotator_id,
            text=state_data["comment"],
        )
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("Expert requested re-annotation of the study")
    await state.clear()
    await cq.message.edit_text("Успешный запрос доразметки - разметчик получил ваш комментарий ✅")


async def pre_expert_annotate(cq: types.CallbackQuery, callback_data: PreExpertAnno, state: FSMContext) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)

    await state.set_state(ExpertPreAnno.waiting_for_conslusion)
    await state.update_data(study_id=callback_data.study_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить", callback_data=ExpertAnno(study_id=callback_data.study_id))
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=callback_data.study_id))
    reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
    await cq.message.edit_text(text="Напишите комментарий разметчику", reply_markup=reply_markup)


async def conslusion_for_annotator_writen(msg: types.Message, state: FSMContext) -> None:
    state_data = await state.update_data(text=msg.text)
    text = as_list(
        Bold("Текст для разметчика"),
        Text(msg.text),
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="Отправить", callback_data=ExpertAnno(study_id=state_data["study_id"]))
    kb.button(text="Отмена", callback_data=AnnoReview(study_id=state_data["study_id"]))
    reply_markup = kb.adjust(1).as_markup()
    await state.set_state(ExpertPreAnno.waiting_for_confirmation)
    await msg.answer(**text.as_kwargs(), reply_markup=reply_markup)


async def expert_annotate(
    cq: types.CallbackQuery,
    callback_data: ExpertAnno | ApproveWithSelfAnno,
    callback_answer: CallbackAnswer,
    state: FSMContext,
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
        assert cq.bot

    study_id = callback_data.study_id
    if cq.from_user is None:
        return

    async with uow:
        study = await uow.studies.get_by_id(study_id)
        if not study:
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return
        path_for_upload = study.study_path.replace("1-original-data", "2-check")
        new_iteration_count = study.iteration_count + 1
        upload_folder_name = f"version_{new_iteration_count}"

        await nc_util.create_folder(path=path_for_upload, new_folder=upload_folder_name)
        upload_link = await nc_util.create_public_link(
            path=f"{path_for_upload}/{upload_folder_name}",
            label=f"Upload for tg-id={cq.from_user.id}",
            permissions=7,
        )

        study.nc_last_upload_link = study.nc_upload_link
        study.nc_upload_link = upload_link
        study.iteration_count = new_iteration_count
        await uow.commit()

    text = get_assigned_study_text(study)
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Закрыть",
        callback_data=ExpertCloseAnno(
            study_id=study_id,
            study_status=StudyStatusEnum.CLOSED_F
            if isinstance(callback_data, ExpertAnno)
            else StudyStatusEnum.APPROVED_F,
        ),
    )
    reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
    await cq.message.edit_text(**text.as_kwargs(), reply_markup=reply_markup)
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        if isinstance(callback_data, ExpertAnno):
            logger.info("Expert rejected annotation v3 and self-assigned the task")
        else:
            logger.info("Expert approved the annotation and proceeded to add minor annotations.")

    if isinstance(callback_data, ExpertAnno):
        if TYPE_CHECKING:
            assert study.annotator_id
        state_data = await state.get_data()
        text = as_list(
            Text("🔹 Эксперт самостоятельно разметит исследование"),
            as_line(Bold("study_iuid: "), Code(study.study_iuid)),
            as_line(Bold("Комментарий: "), state_data.get("text", "-")),
        )
        await cq.bot.send_message(
            chat_id=study.annotator_id,
            **text.as_kwargs(),
        )
        callback_answer.text = "Сообщение отправлено разметчику ✅"
        await state.clear()


async def expert_annotate_finish(
    cq: types.CallbackQuery,
    callback_data: ExpertCloseAnno,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
        assert cq.bot

    study_id = callback_data.study_id
    async with uow:
        study = await uow.studies.get_by_id(study_id)
        if not study:
            return
        if not study.annotator_id:
            callback_answer.text, callback_answer.show_alert = "Ошибка - у разметки нет разметчика", True
            return
        study_iteration = study.iteration_count
        upload_path = study.study_path.replace("1-original-data", "2-check")
        annotate_path = f"{upload_path}/version_{study_iteration}"

    empty = await nc_util.is_directory_empty(path=annotate_path)
    if empty:
        callback_answer.text, callback_answer.show_alert = "Вы ничего не выгрузили", True
        return

    async with uow:
        study = await uow.studies.update(
            study_id,
            {
                "status": callback_data.study_status,
            },
        )
        if not study:
            callback_answer.text, callback_answer.show_alert = "Ошибка - нет такого исследования", True
            return
        await uow.commit()

    text = as_list(
        get_assigned_study_text(study),
        Text("Закрыто ✅"),
        sep="\n\n",
    )
    await cq.message.edit_text(**text.as_kwargs())
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("Expert finished the annotation personally")

    upload_path = study.study_path.replace("1-original-data", "2-check")
    latest_upload = f"{upload_path}/version_{study_iteration}"
    dst_path = upload_path.replace("2-check", "3-research")
    await nc_util.copy_directory(src_dir=latest_upload, dst_dir=dst_path)
    with logger.contextualize(study_iuid=study.study_iuid, iteration_count=study.iteration_count):
        logger.info("The latest annotation version was copied to the 3-research directory")


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.callback_query.register(annotate_review, or_f(StudyAnnoReview.filter(), StudyReportReview.filter()))
    router.callback_query.register(rework_review_start, ExpertReworkReview.filter())
    router.callback_query.register(approve_anno, ApproveAnno.filter())
    router.callback_query.register(annotate_review_view_only, AnnoReview.filter())
    router.callback_query.register(approve_anno_confirmed, ConfirmApproveAnno.filter())

    router.callback_query.register(close_anno, CloseAnno.filter())
    router.callback_query.register(close_anno_reason_choosen, CloseAnnoReason.filter())

    reject_router = Router(name=__name__ + "_reject")
    reject_router.message.middleware.register(MediaGroupMiddleware())
    reject_router.callback_query.register(reject_annotate, RejectAnno.filter())
    reject_router.message.register(reject_comment_writen, F.text, RejectState.waiting_for_comment)
    reject_router.message.register(reject_new_photos, F.media_group_id, RejectState.waiting_for_screenshots)
    reject_router.message.register(reject_new_photo, F.photo, RejectState.waiting_for_screenshots)
    reject_router.callback_query.register(send_reject, F.data == "send", RejectState.waiting_for_screenshots)
    router.include_router(reject_router)

    router.callback_query.register(pre_expert_annotate, PreExpertAnno.filter())
    router.message.register(conslusion_for_annotator_writen, F.text, ExpertPreAnno.waiting_for_conslusion)
    router.callback_query.register(expert_annotate, or_f(ExpertAnno.filter(), ApproveWithSelfAnno.filter()))
    router.callback_query.register(expert_annotate_finish, ExpertCloseAnno.filter())

    dp.include_router(router)
