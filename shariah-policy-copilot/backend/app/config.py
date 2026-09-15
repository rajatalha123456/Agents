from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Storage
    database_url: str = "sqlite:///./data/copilot.db"
    vector_store_dir: str = "./data/vector_store"
    raw_docs_dir: str = "./data/raw_documents"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # LLM
    llm_provider: str = "anthropic"  # "anthropic" | "gemini" | "ollama"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ollama_model: str = "llama3.1"
    ollama_host: str = "http://localhost:11434"

    # Retrieval
    top_k_semantic: int = 16
    top_k_keyword: int = 50
    top_k_final: int = 20

    # Auth
    secret_key: str = "change_me_dev_only"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

# Fixed strings the requirements doc mandates verbatim (FR-15, FR-16) —
# keep these here, not scattered in code, so audit/legal can review them in one place.
DISCLAIMER_TEXT = (
    "This research output does not constitute a fatwa or final Shariah "
    "determination. Human Shariah review is required."
)

NO_EVIDENCE_FALLBACK = (
    "No approved internal Shariah ruling or standard was found that addresses "
    "this question. This matter should be referred to a designated Shariah "
    "reviewer for a fresh determination. No general or external knowledge has "
    "been used to answer this query."
)
