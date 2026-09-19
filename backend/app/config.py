from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "trustcircle"

    # Trust tier thresholds (unique repeat customers)
    TIER_GROWING_MIN: int = 5
    TIER_TRUSTED_MIN: int = 50
    TIER_COMMUNITY_MIN: int = 500

    # K-anonymity floor
    K_ANONYMITY_FLOOR: int = 5

    # A customer must scan >= this many times to count as "repeat"
    REPEAT_SCAN_THRESHOLD: int = 3


settings = Settings()
