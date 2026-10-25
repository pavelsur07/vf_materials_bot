from pydantic import BaseModel, ConfigDict, Field


class LeadNotificationIn(BaseModel):
    """Notification text built by the site. The bot relays it into Telegram as-is."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "Новая заявка с сайта vashfindir.ru\n"
                        "Имя: Иван Петров\n"
                        "Телефон: +7 900 123-45-67\n"
                        "Комментарий: Прошу перезвонить после 18:00"
                    )
                }
            ]
        }
    )

    text: str = Field(
        min_length=1,
        max_length=4000,
        description="Готовый текст уведомления — бот перешлёт его в Telegram без изменений",
    )
