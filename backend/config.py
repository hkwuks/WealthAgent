from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "智能理财Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    API_PREFIX: str = "/api"
    
    CORS_ORIGINS: list = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    DATA_DIR: str = "data"
    
    TUSHARE_TOKEN: Optional[str] = None

    FRED_API_KEY: Optional[str] = None

    MODEL_DIR: str = "data/models"
    MODEL_MAX_AGE_DAYS: int = 7
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
