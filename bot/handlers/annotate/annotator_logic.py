import asyncio
from typing import TYPE_CHECKING, cast

from aiogram import Dispatcher, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.callback_answer import CallbackAnswer
from aiogram.utils.formatting import Bold, Code, Text, TextLink, as_line, as_list
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dishka.integrations.aiogram import FromDishka
from loguru import logger

from bot.handlers.annotate.utils import (
    ChooseCategoriesAnno,
    ChooseProjectCallback,
    ExpertReworkReview,
    ReAnnoStudy,
    ReportReasons,
    StudyAnnoReview,
    StudyAnnoReviewRequest,
    StudyAnnoReviewReRequest,
    StudyReport,
    StudyReportReason,
    StudyReportReview,
    get_assigned_study_kb,
    get_assigned_study_text,
)
from core.models.study import StudyStatusEnum
from core.unit_of_work import IUnitOfWork
from core.utils.nextcloud import NextcloudUtils


async def command_task(msg: types.Message, uow: FromDishka[IUnitOfWork]) -> None:
    if msg.from_user is None:
        logger.debug("Received /task command without from_user payload")
        return

    user_id = msg.from_user.id
    text: Text
    async with uow:
        user = await uow.users.get_by_tg_id_with_projects(tg_id=msg.from_user.id)
        if not user:
            logger.debug("User ({}) is not registered", user_id)
            return
        study = await uow.studies.get_assigned_for_annotator(user_id=user_id)
        if study:
            if study.status == StudyStatusEnum.WAITING_REWORK:
                text = Text("❗️ У вас есть исследования для переразметки, поищите их выше")
                reply_markup = None
            else:
                text = get_assigned_study_text(study)
                reply_markup = get_assigned_study_kb(study)
        else:
            text = as_list(
                Bold("🔹 Назначение задачи"),
                Text("Выберите проект"),
            )
            kb = InlineKeyboardBuilder()
            for project in user.projects:
                kb.button(text=project.name, callback_data=ChooseProjectCallback(project_id=project.id))
            reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(2).as_markup())

    await msg.answer(**text.as_kwargs(), reply_markup=reply_markup)


async def callback_command_task(cq: types.CallbackQuery, uow: FromDishka[IUnitOfWork], state: FSMContext) -> None:
    await state.clear()

    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)

    if cq.from_user is None:
        logger.debug("Received /task command without from_user payload")
        return

    user_id = cq.from_user.id
    text: Text
    async with uow:
        user = await uow.users.get_by_tg_id_with_projects(tg_id=user_id)
        if not user:
            logger.debug("User ({}) is not registered", user_id)
            return
        active_study = await uow.studies.get_assigned_for_annotator(user_id=user_id)
        if active_study:
            text = get_assigned_study_text(active_study)
            reply_markup = get_assigned_study_kb(active_study)
        else:
            text = as_list(
                Bold("🔹 Назначение задачи"),
                Text("Выберите проект"),
            )
            kb = InlineKeyboardBuilder()
            for project in user.projects:
                kb.button(text=project.name, callback_data=ChooseProjectCallback(project_id=project.id))
            reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(2).as_markup())

    await cq.message.edit_text(**text.as_kwargs(), reply_markup=reply_markup)


async def assign_annotate_to_user(
    cq: types.CallbackQuery,
    callback_data: ChooseProjectCallback,
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)

    project_id = callback_data.project_id
    if cq.from_user is None:
        logger.warning("Received callback command without from_user payload")
        return

    async with uow:
        study = await uow.studies.assign_to_user(
            project_id=project_id,
            user_id=cq.from_user.id,
        )
        if not study:
            text = as_list(
                Bold("Назначение задачи"),
                Text("Нет исследований для разметки, попробуйте позже"),
            )
            reply_markup = None
            with logger.contextualize(user_id=cq.from_user.id):
                logger.info("No studies available for annotation")
        else:
            share_link = await nc_util.create_public_link(
                path=study.study_path,
                label=f"Public View for tg-id={cq.from_user.id}",
                permissions=1,
            )

            path_for_upload = study.study_path.replace("1-original-data", "2-check")
            upload_folder_name = f"version_{study.iteration_count}"
            await nc_util.create_folder(path=path_for_upload, new_folder=upload_folder_name)
            upload_link = await nc_util.create_public_link(
                path=f"{path_for_upload}/{upload_folder_name}",
                label=f"Upload for tg-id={cq.from_user.id}",
                permissions=7,  # Upload
            )

            study.nc_share_link = share_link
            study.nc_upload_link = upload_link
            await uow.commit()

            text = get_assigned_study_text(study)
            reply_markup = get_assigned_study_kb(study)
            with logger.contextualize(user_id=cq.from_user.id, study_iuid=study.study_iuid):
                logger.info("A study was assigned to the user for annotation")

    await cq.message.edit_text(**text.as_kwargs(), reply_markup=reply_markup)


async def choose_categories(
    cq: types.CallbackQuery,
    callback_data: ChooseCategoriesAnno,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    state: FSMContext,
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)

    chosed = await state.get_value("choosed_categories")
    if not chosed:
        chosed = []
    if callback_data.category_id:
        if callback_data.category_id in chosed:
            chosed.remove(callback_data.category_id)
        else:
            chosed.append(callback_data.category_id)
    await state.update_data(choosed_categories=chosed)

    categories_missing = False
    kb = InlineKeyboardBuilder()
    async with uow:
        batch = await uow.batches.get_with_categories(batch_id=callback_data.batch_id)
        if not batch:
            callback_answer.text, callback_answer.show_alert = "Ошибка - батч не найден", True
            return
        if not batch.categories:
            categories_missing = True
        else:
            for category in batch.categories:
                kb.button(
                    text=f"✅ {category.name}" if category.id in chosed else category.name,
                    callback_data=ChooseCategoriesAnno(
                        study_id=callback_data.study_id,
                        batch_id=batch.id,
                        category_id=category.id,
                    ),
                )
    if categories_missing:
        await annotate_review_request(
            cq,
            StudyAnnoReviewRequest(study_id=callback_data.study_id),
            callback_answer,
            uow,
            state,
            nc_util,
        )
        return
    kb.button(text="✅ Подтвердить", callback_data=StudyAnnoReviewRequest(study_id=callback_data.study_id))
    kb.button(text="↩️ Отмена", callback_data="task")
    reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())

    text = "🔹 Выберите класс исследования\n* либо сразу нажмите кнопку 'Подтвердить' без выбора класса"
    await cq.message.edit_text(text=text, reply_markup=reply_markup)


review_request_lock = asyncio.Lock()


async def annotate_review_request(
    cq: types.CallbackQuery,
    callback_data: StudyAnnoReviewRequest,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    state: FSMContext,
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert cq.bot
        assert isinstance(cq.message, types.Message)

    study_id = callback_data.study_id
    category_ids = await state.get_value("choosed_categories")
    async with review_request_lock, uow:
        study = await uow.studies.get_with_categories(study_id)
        if not study:
            logger.error("Study with id {} not found", study_id)
            callback_answer.text, callback_answer.show_alert = "Ошибка - исследование не найдено", True
            return
        if study.status not in (StudyStatusEnum.ASSIGNED, StudyStatusEnum.REWORK):
            with logger.contextualize(
                user_id=cq.from_user.id,
                study_iuid=study.study_iuid,
                iteration_count=study.iteration_count,
            ):
                logger.debug("Double review request detected, skip")
            return

        study_iteration = study.iteration_count
        upload_path = study.study_path.replace("1-original-data", "2-check")
        annotate_path = f"{upload_path}/version_{study_iteration}"
        empty = await nc_util.is_directory_empty(path=annotate_path)
        if empty:
            callback_answer.text, callback_answer.show_alert = "Вы ничего не выгрузили", True
            return

        study.categories.clear()
        if category_ids:
            categories = await uow.categories.get_by_ids(category_ids)
            study.categories.extend(categories)

        study.status = StudyStatusEnum.WAITING_REVIEW

        project = await uow.projects.get_by_batch_id(batch_id=study.batch_id)
        if not project:
            logger.error("Project for batch_id={} not found", study.batch_id)
            callback_answer.text, callback_answer.show_alert = "Ошибка - проект не найден", True
            return

        annotator = await uow.users.get_by_id(cq.from_user.id)
        if not annotator:
            callback_answer.text, callback_answer.show_alert = "Вы не зарегистрированы в боте!", True
            return

        await uow.commit()

    test = as_list(
        Bold("✏️ Требуется подтверждение разметки"),
        as_line(Bold("study_uiud: "), Code(study.study_iuid)),
        as_line(
            Bold("Разметчик: "),
            as_line(
                TextLink(annotator.name, url=f"tg://user?id={annotator.tg_id}"),
                Text(f" (@{annotator.tg_username})") if annotator.tg_username else Text(),
            ),
        ),
        sep="\n",
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="Взять в работу", callback_data=StudyAnnoReview(study_id=study.id))
    reply_markup = kb.adjust(1).as_markup()
    await cq.bot.send_message(
        chat_id=project.tg_group_id,
        **test.as_kwargs(),
        reply_markup=reply_markup,
    )

    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("User requested an annotation review")

    text = as_list(get_assigned_study_text(study), as_line(Bold("UPD: "), Text("отправлено на проверку")))
    await cq.message.edit_text(**text.as_kwargs())
    callback_answer.text = "Запрос на проверку успешно отправлен ✅"

    await state.clear()


async def report_study(cq: types.CallbackQuery, callback_data: StudyReport) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)
    study_id = callback_data.study_id
    text = as_list(Bold("report"), Text("Выберите причину"), sep="\n\n")
    kb = InlineKeyboardBuilder()
    kb.button(text="Normal", callback_data=StudyReportReason(study_id=study_id, reason=ReportReasons.NORMAL))
    kb.button(text="Incorrect", callback_data=StudyReportReason(study_id=study_id, reason=ReportReasons.INCORRECT))
    kb.button(text="Other", callback_data=StudyReportReason(study_id=study_id, reason=ReportReasons.OTHER_PATHOLOGY))
    kb.button(text="Отмена", callback_data="task")
    reply_markup = cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
    await cq.message.edit_text(**text.as_kwargs(), reply_markup=reply_markup)


async def report_study_reason_choosen(
    cq: types.CallbackQuery,
    callback_data: StudyReportReason,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
) -> None:
    if TYPE_CHECKING:
        assert cq.bot
        assert isinstance(cq.message, types.Message)

    async with uow:
        study = await uow.studies.get_by_id(callback_data.study_id)
        if not study:
            logger.error("Study with id={} is not found", callback_data.study_id)
            callback_answer.text = "Ошибка - исследование не найдено"
            return
        await uow.studies.update(
            study.id,
            {
                "status": StudyStatusEnum.PENDING_CONFIRMATION,
            },
        )
        project = await uow.projects.get_by_batch_id(batch_id=study.batch_id)
        if not project:
            logger.error("Project for batch with id={} is not found", study.batch_id)
            callback_answer.text = "Ошибка - проект не найден"
            return
        annotator = await uow.users.get_by_id(cq.from_user.id)
        if not annotator:
            callback_answer.text, callback_answer.show_alert = "Вы не зарегистрированы в боте!", True
            return
        await uow.commit()

    test = as_list(
        Bold("Требуется подтверждение"),
        as_line(Bold("study_uiud: "), Code(study.study_iuid)),
        as_line(Bold("Причина: "), Code(callback_data.reason.name)),
        as_line(
            Bold("Разметчик: "),
            as_line(
                TextLink(annotator.name, url=f"tg://user?id={annotator.tg_id}"),
                Text(f" (@{annotator.tg_username})") if annotator.tg_username else Text(),
            ),
        ),
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="Взять в работу", callback_data=StudyReportReview(study_id=study.id, reason=callback_data.reason))
    reply_markup = kb.adjust(1).as_markup()
    await cq.bot.send_message(
        chat_id=project.tg_group_id,
        **test.as_kwargs(),
        reply_markup=reply_markup,
    )
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("The user sent reject for study")

    text = as_list(get_assigned_study_text(study), as_line(Bold("UPD: "), Text("отправлено на проверку")))
    await cq.message.edit_text(**text.as_kwargs())
    callback_answer.text = "Запрос на проверку успешно отправлен ✅"


async def reannotate(
    cq: types.CallbackQuery,
    callback_data: ReAnnoStudy,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert isinstance(cq.message, types.Message)

    study_id = callback_data.study_id
    if cq.from_user is None:
        logger.debug("Received callback command without from_user payload")
        return

    async with uow:
        study = await uow.studies.get_by_id(study_id)
        if not study:
            logger.error("Study with id {} not found", study_id)
            callback_answer.text, callback_answer.show_alert = "Ошибка - исследование не найдено", True
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
        study.status = StudyStatusEnum.REWORK
        await uow.commit()

    text = get_assigned_study_text(study)
    reply_markup = get_assigned_study_kb(study)
    await cq.message.reply(**text.as_kwargs(), reply_markup=reply_markup)
    await cq.message.edit_text(text=cq.message.html_text + "\n\nВзято в работу ✅")
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("User took studies for re-annotation")


reannotate_review_request_lock = asyncio.Lock()


async def reannotate_review_request(
    cq: types.CallbackQuery,
    callback_data: StudyAnnoReviewReRequest,
    callback_answer: CallbackAnswer,
    uow: FromDishka[IUnitOfWork],
    nc_util: FromDishka[NextcloudUtils],
) -> None:
    if TYPE_CHECKING:
        assert cq.bot
        assert isinstance(cq.message, types.Message)

    study_id = callback_data.study_id
    async with reannotate_review_request_lock, uow:
        study = await uow.studies.get_by_id(study_id)
        if not study:
            logger.error("Study with id={} is not found", callback_data.study_id)
            callback_answer.text = "Ошибка - исследование не найдено"
            return
        if study.status != StudyStatusEnum.REWORK:
            with logger.contextualize(
                user_id=cq.from_user.id,
                study_iuid=study.study_iuid,
                iteration_count=study.iteration_count,
            ):
                logger.debug("Double review request detected, skip")
            return
        study.status = StudyStatusEnum.WAITING_REVIEW
        if study.expert_id is None:
            logger.error("Expert for study with id={} is not found", callback_data.study_id)
            callback_answer.text = "Ошибка - исследованию не назначен эксперт"
            return
        await uow.commit()

    study_iteration = study.iteration_count
    upload_path = study.study_path.replace("1-original-data", "2-check")
    annotate_path = f"{upload_path}/version_{study_iteration}"
    empty = await nc_util.is_directory_empty(path=annotate_path)
    if empty:
        callback_answer.text, callback_answer.show_alert = "Вы ничего не выгрузили", True
        return

    text: Text = as_list(
        Bold("🔹 Проверка разметки") if study.iteration_count == 1 else Bold("🔺 Перепроверка разметки"),
        as_line(Bold("StudyIUID: "), Code(study.study_iuid)),
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="Взять в работу", callback_data=ExpertReworkReview(study_id=study_id))
    reply_markup = kb.as_markup()
    await cq.bot.send_message(
        chat_id=study.expert_id,
        **text.as_kwargs(),
        reply_markup=reply_markup,
        reply_to_message_id=study.reject_comment_msg_id,
    )
    with logger.contextualize(
        user_id=cq.from_user.id,
        study_iuid=study.study_iuid,
        iteration_count=study.iteration_count,
    ):
        logger.info("User submitted a new annotation version for review")

    text = as_list(get_assigned_study_text(study), as_line(Bold("UPD: "), Text("отправлено на проверку")))
    await cq.message.edit_text(**text.as_kwargs())
    callback_answer.text = "Запрос на проверку успешно отправлен ✅"


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name=__name__)
    router.message.register(command_task, Command("task"))
    router.callback_query.register(assign_annotate_to_user, ChooseProjectCallback.filter())
    router.callback_query.register(choose_categories, ChooseCategoriesAnno.filter())
    router.callback_query.register(annotate_review_request, StudyAnnoReviewRequest.filter())

    router.callback_query.register(report_study, StudyReport.filter())
    router.callback_query.register(report_study_reason_choosen, StudyReportReason.filter())
    router.callback_query.register(callback_command_task, F.data == "task")
    router.callback_query.register(reannotate, ReAnnoStudy.filter())
    router.callback_query.register(reannotate_review_request, StudyAnnoReviewReRequest.filter())
    dp.include_router(router)
