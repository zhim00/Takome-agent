from app.settings import Settings


def test_settings_reads_single_internal_token() -> None:
    settings = Settings(internal_token="shared-token")

    assert settings.internal_token == "shared-token"
