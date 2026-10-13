from bot.core.config import Settings


def test_blank_leads_topic_id_defaults_to_zero() -> None:
    settings = Settings.model_validate({"leads_topic_id": ""})

    assert settings.leads_topic_id == 0


def test_blank_leads_chat_id_defaults_to_zero() -> None:
    settings = Settings.model_validate({"leads_chat_id": ""})

    assert settings.leads_chat_id == 0
