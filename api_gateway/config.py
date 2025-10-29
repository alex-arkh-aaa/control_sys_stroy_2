from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):

    

    class Config:
        env_file = Path(__file__).parent / ".env"

settings = Settings()

