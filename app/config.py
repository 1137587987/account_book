from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    FEISHU_APP_ID: str
    FEISHU_APP_SECRET: str
    FEISHU_VERIFICATION_TOKEN: str
    FEISHU_ENCRYPT_KEY: str = ""

    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str
    LLM_MODEL: str = "gpt-4o-mini"

    EMAIL_SENDER: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_RECIPIENTS: str = ""

    DATABASE_PATH: str = "./data/accout_book.db"

    @property
    def DATABASE_URL(self) -> str:
        return f"sqlite+aiosqlite:///{self.DATABASE_PATH}"

    @property
    def email_recipient_list(self) -> list[str]:
        return [e.strip() for e in self.EMAIL_RECIPIENTS.split(",") if e.strip()]


settings = Settings()
