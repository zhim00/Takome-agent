from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_BASE_URL",
    )
    spring_base_url: str = Field(
        default="http://localhost:8888",
        alias="SPRING_BASE_URL",
    )
    internal_token: str = Field(default="", alias="INTERNAL_TOKEN")
    thread_ttl_seconds: int = Field(default=1800, alias="THREAD_TTL_SECONDS")
    max_message_length: int = Field(default=2000, alias="MAX_MESSAGE_LENGTH")
    disable_deepseek_thinking: bool = Field(
        default=True,
        alias="DISABLE_DEEPSEEK_THINKING",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("deepseek_model")
    @classmethod
    def reject_legacy_deepseek_aliases(cls, value: str) -> str:
        disallowed = {"deepseek-chat", "deepseek-reasoner"}
        if value in disallowed:
            raise ValueError(
                "Use a DeepSeek V4 model name such as deepseek-v4-flash, "
                "not deepseek-chat or deepseek-reasoner."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
