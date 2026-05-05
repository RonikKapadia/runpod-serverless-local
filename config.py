from pydantic_settings import BaseSettings
from src import EndpointConfig

class Config(BaseSettings):
    ENDPOINTS: list[EndpointConfig]

CONFIG = Config() # type: ignore