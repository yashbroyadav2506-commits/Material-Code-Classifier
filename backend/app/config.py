from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./nmc_local.db"

    llm_provider: str = "auto"          # auto | openai | anthropic | mock
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    match_weights_text: float = 0.15
    match_weights_attr: float = 0.45
    match_weights_category: float = 0.15
    match_weights_unit: float = 0.10
    match_weights_mfr: float = 0.15

    # Bulk candidate generation runs the fast local hybrid engine by default.
    # Set true to also call the LLM per pair (slow, costly) during batch runs.
    llm_refine_matching_bulk: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()