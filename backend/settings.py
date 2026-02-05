from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QA_")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/questionnaire"
    chroma_path: str = "storage/chroma"
    storage_path: str = "storage/documents"

    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2"
    embed_model: str = "nomic-embed-text"

    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 5
    min_similarity: float = 0.25


settings = Settings()
