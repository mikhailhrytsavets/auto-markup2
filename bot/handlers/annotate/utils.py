from enum import StrEnum
from typing import cast

from aiogram import types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.formatting import Bold, Code, Text, Url, as_line, as_list
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.models.study import Study, StudyStatusEnum


class ReportReasons(StrEnum):
    NORMAL = "n"
    INCORRECT = "i"
    OTHER_PATHOLOGY = "op"


class ChooseProjectCallback(CallbackData, prefix="task-for-project"):
    project_id: int


class StudyAnnoReviewRequest(CallbackData, prefix="study-anno-review-req"):
    study_id: int


class StudyAnnoReviewReRequest(CallbackData, prefix="study-anno-review-rereq"):
    study_id: int


class StudyAnnoReview(CallbackData, prefix="study-anno-review"):
    study_id: int


class StudyReportReview(CallbackData, prefix="study-report-review"):
    study_id: int
    reason: ReportReasons


class StudyReport(CallbackData, prefix="study-report"):
    study_id: int


class StudyReportReason(CallbackData, prefix="study-report-reason"):
    study_id: int
    reason: ReportReasons


class ApproveAnno(CallbackData, prefix="approve-anno"):
    study_id: int


class ConfirmApproveAnno(CallbackData, prefix="confirm-approve-anno"):
    study_id: int


class ApproveWithSelfAnno(CallbackData, prefix="approve-with-self-anno"):
    study_id: int


class AnnoReview(CallbackData, prefix="annotate-review"):
    study_id: int


class RejectAnno(CallbackData, prefix="reject-anno"):
    study_id: int


class ReAnnoStudy(CallbackData, prefix="re-anno-study"):
    study_id: int


class CloseAnno(CallbackData, prefix="close-anno"):
    study_id: int


class CloseAnnoReason(CallbackData, prefix="close-anno-reason"):
    study_id: int
    reason: ReportReasons


class PreExpertAnno(CallbackData, prefix="pre-expert-anno"):
    study_id: int


class ExpertAnno(CallbackData, prefix="expert-anno"):
    study_id: int


class ExpertCloseAnno(CallbackData, prefix="expert-close-anno"):
    study_id: int
    study_status: StudyStatusEnum


class ExpertReworkReview(CallbackData, prefix="expert-rework-review"):
    study_id: int


def get_assigned_study_text(study: Study) -> Text:
    text: Text = as_list(
        Bold("Вам назначено исследование для разметки"),
        as_line(Bold("StudyIUID: "), Code(study.study_iuid)),
        as_line(Bold("Номер папки: "), Code(study.study_path.rsplit("/", maxsplit=1)[1])),
        as_line(Bold("Номер итерации: "), Code(study.iteration_count)),
        as_line(Bold("Скачать: "), Url(study.nc_share_link)),
        as_line(Bold("Для выгрузки: "), Url(study.nc_upload_link)),
        as_line(Bold("* Прошлая выгрузка: "), Url(study.nc_last_upload_link)) if study.nc_last_upload_link else Text(),
    )
    return text


def get_assigned_study_kb(study: Study) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    callback_data_class: type[StudyAnnoReviewRequest | StudyAnnoReviewReRequest]
    if study.status == StudyStatusEnum.ASSIGNED:
        callback_data_class = StudyAnnoReviewRequest
    else:
        callback_data_class = StudyAnnoReviewReRequest
    kb.button(text="👁️‍🗨️ Запросить проверку", callback_data=callback_data_class(study_id=study.id))
    kb.button(text="Отклонить", callback_data=StudyReport(study_id=study.id))
    return cast("types.InlineKeyboardMarkup", kb.adjust(1).as_markup())
