import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    data_dir: Path = Path(os.getenv('RISK_DATA_DIR', 'runtime'))
    admin_key: str = os.getenv('ADMIN_API_KEY', '')
    llm_provider: str = os.getenv('LLM_PROVIDER', 'none')
    llm_url: str = os.getenv('LLM_BASE_URL', 'http://localhost:11434')
    llm_model: str = os.getenv('LLM_MODEL', 'qwen3')
    llm_key: str = os.getenv('LLM_API_KEY', '')
    openai_key: str = os.getenv('OPENAI_API_KEY', '')
    openai_model: str = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
    external_llm: bool = os.getenv('ALLOW_EXTERNAL_LLM', 'false').lower() == 'true'
    max_upload_mb: int = int(os.getenv('MAX_UPLOAD_MB', '20'))
    rate_limit: int = int(os.getenv('RATE_LIMIT_PER_MINUTE', '120'))
