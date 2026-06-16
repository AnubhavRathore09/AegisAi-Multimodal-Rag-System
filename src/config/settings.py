from __future__ import annotations

from pathlib import Path

import yaml

from src.config import DATA_DIR, FAISS_DIR, STORAGE_DIR, UPLOAD_DIR, Settings, settings as app_settings

BASE_DIR = Path(__file__).resolve().parents[2]
PROMPT_FILE = BASE_DIR / 'prompt.yaml'


class Config:
    DATA_DIR = str(DATA_DIR)
    STORAGE_DIR = str(STORAGE_DIR)
    VECTOR_DB_DIR = str(FAISS_DIR)
    UPLOAD_DIR = str(UPLOAD_DIR)
    MODEL_NAME = app_settings.model_name
    EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
    GEMINI_API_KEY = app_settings.gemini_api_key
    GEMINI_BASE_URL = app_settings.gemini_base_url
    MODEL_FALLBACK = app_settings.fallback_model_name

    def prompt(self, prompt_template: str) -> str:
        template = self._load_prompt(prompt_template)
        if template:
            return template
        return (
            'Assistant name: {bot_name}\n\n'
            'Context:\n{context}\n\n'
            'User question:\n{question}\n'
        )

    def _load_prompt(self, prompt_template: str) -> str:
        if not PROMPT_FILE.exists():
            return ''
        try:
            payload = yaml.safe_load(PROMPT_FILE.read_text(encoding='utf-8'))
        except Exception:
            return ''
        if not isinstance(payload, dict):
            return ''
        prompts = payload.get('prompts', payload)
        if not isinstance(prompts, dict):
            return ''
        allowed_template = prompt_template if prompt_template in {'generate_prompt', 'live_news_prompt'} else 'generate_prompt'
        value = prompts.get(allowed_template) or prompts.get('generate_prompt')
        return str(value).strip() if value else ''


# Module-level compatibility aliases for older imports that accidentally treat
# `src.config.settings` like the runtime settings object.
gemini_api_key = app_settings.gemini_api_key
gemini_base_url = app_settings.gemini_base_url
model_name = app_settings.model_name
fallback_model_name = app_settings.fallback_model_name
router_model_name = app_settings.router_model_name
summary_model_name = app_settings.summary_model_name
transcription_model_name = app_settings.transcription_model_name
tavily_api_key = app_settings.tavily_api_key
tavily_max_results = app_settings.tavily_max_results
mongodb_uri = app_settings.mongodb_uri
mongodb_db = app_settings.mongodb_db
