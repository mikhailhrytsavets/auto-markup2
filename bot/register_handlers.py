from aiogram import Dispatcher

from bot.handlers.admin.add_project import register_handlers as add_project_handlers
from bot.handlers.admin.add_user_to_project import register_handlers as add_validator_to_project
from bot.handlers.admin.cancel_task import register_handlers as cancel_task
from bot.handlers.admin.generate_reg_link import register_handlers as admin_handlers
from bot.handlers.annotate.annotator_logic import register_handlers as tasks_handlers
from bot.handlers.annotate.validator_logic import register_handlers as expert_review
from bot.handlers.common import register_handlers as common_handlers
from bot.handlers.registration import register_handlers as registration_handlers


def register_handlers(dp: Dispatcher) -> None:
    admin_handlers(dp=dp)
    registration_handlers(dp=dp)
    common_handlers(dp=dp)
    tasks_handlers(dp=dp)
    expert_review(dp=dp)
    add_project_handlers(dp=dp)
    cancel_task(dp=dp)
    add_validator_to_project(dp=dp)
