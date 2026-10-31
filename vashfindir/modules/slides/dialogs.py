from vashfindir.domain.slides import SlideGenerationStatus

SLIDE_STATUS_LABELS = {
    SlideGenerationStatus.QUEUED: "В очереди",
    SlideGenerationStatus.GENERATING: "Генерация",
    SlideGenerationStatus.READY: "Готово",
    SlideGenerationStatus.FAILED: "Ошибка",
}

INVALID_PLOT_MESSAGE = "Сюжет должен содержать от 10 до 1000 символов."
SLIDES_DISABLED_MESSAGE = "Генерация слайдов временно недоступна."


def generation_queued_message(generation_id: int) -> str:
    return f"Генерация №{generation_id} поставлена в очередь."
