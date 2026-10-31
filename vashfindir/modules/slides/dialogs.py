from vashfindir.domain.slides import SlideGenerationStatus

SLIDE_STATUS_LABELS = {
    SlideGenerationStatus.QUEUED: "В очереди",
    SlideGenerationStatus.GENERATING: "Генерация",
    SlideGenerationStatus.READY: "Готово",
    SlideGenerationStatus.FAILED: "Ошибка",
}

SLIDE_STATUS_DESCRIPTIONS = {
    SlideGenerationStatus.QUEUED: "Задача создана и ждёт запуска worker.",
    SlideGenerationStatus.GENERATING: (
        "OpenAI создаёт изображение. Обычно это занимает до 1–2 минут."
    ),
    SlideGenerationStatus.READY: "Изображение готово и доступно для скачивания.",
    SlideGenerationStatus.FAILED: "Генерация завершилась ошибкой. Можно попробовать ещё раз.",
}

INVALID_PLOT_MESSAGE = "Сюжет должен содержать от 10 до 1000 символов."
SLIDES_DISABLED_MESSAGE = "Генерация слайдов временно недоступна."
GENERATION_ALREADY_RUNNING_MESSAGE = "Генерация уже выполняется. Дождитесь завершения."


def generation_queued_message(generation_id: int) -> str:
    return f"Генерация №{generation_id} поставлена в очередь."
