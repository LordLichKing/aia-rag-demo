import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


_config_instance: Optional["Settings"] = None


class Settings:
    def __init__(self, config_path: str = "config.yaml"):
        self._raw = self._load_config(config_path)
        self._resolve_env_vars(self._raw)

    @staticmethod
    def _load_config(config_path: str) -> Dict[str, Any]:
        path = Path(config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    @staticmethod
    def _resolve_env_vars(d: Dict[str, Any]) -> None:
        for key, value in d.items():
            if isinstance(value, dict):
                Settings._resolve_env_vars(value)
            elif isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                inner = value[2:-1]
                default = None
                if ":" in inner:
                    env_name, default_expr = inner.split(":", 1)
                    default = default_expr
                else:
                    env_name = inner
                d[key] = os.environ.get(env_name, default or value)

    @property
    def app(self) -> Dict[str, Any]:
        return self._raw.get("app", {})

    @property
    def elasticsearch(self) -> Dict[str, Any]:
        return self._raw.get("elasticsearch", {})

    @property
    def embedding(self) -> Dict[str, Any]:
        return self._raw.get("embedding", {})

    @property
    def llm(self) -> Dict[str, Any]:
        return self._raw.get("llm", {})

    @property
    def retrieval(self) -> Dict[str, Any]:
        return self._raw.get("retrieval", {})

    @property
    def chunking(self) -> Dict[str, Any]:
        return self._raw.get("chunking", {})

    @property
    def safety(self) -> Dict[str, Any]:
        return self._raw.get("safety", {})

    @property
    def cache(self) -> Dict[str, Any]:
        return self._raw.get("cache", {})

    @property
    def logging(self) -> Dict[str, Any]:
        return self._raw.get("logging", {})

    @property
    def evaluation(self) -> Dict[str, Any]:
        return self._raw.get("evaluation", {})

    def get(self, key: str, default: Any = None) -> Any:
        return self._raw.get(key, default)


def get_settings(config_path: str = "config.yaml") -> Settings:
    global _config_instance
    if _config_instance is None:
        _config_instance = Settings(config_path)
    return _config_instance
