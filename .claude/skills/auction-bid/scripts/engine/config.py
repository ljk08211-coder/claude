"""config.toml 읽기. 사용자 설정 파일이 있으면 기본값 위에 덮어쓴다."""
import tomllib
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.toml"


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(user_path=None):
    with open(DEFAULT_PATH, "rb") as f:
        cfg = tomllib.load(f)
    if user_path and Path(user_path).exists():
        with open(user_path, "rb") as f:
            cfg = _merge(cfg, tomllib.load(f))
    return cfg
