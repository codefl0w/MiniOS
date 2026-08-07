import os
import re


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENV_PATH = os.path.join(BASE_DIR, ".env")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOADED_PATHS = set()


def _clean_value(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def _parse_line(line):
    line = line.strip().lstrip("\ufeff")
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    if not ENV_KEY_RE.match(key):
        return None
    return key, _clean_value(value)


def load_env(path=None, override=False):
    env_path = os.path.abspath(path or os.environ.get("MINIOS_ENV_PATH") or DEFAULT_ENV_PATH)
    if env_path in _LOADED_PATHS and not override:
        return True
    if not os.path.isfile(env_path):
        return False

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            parsed = _parse_line(line)
            if not parsed:
                continue
            key, value = parsed
            if override or key not in os.environ:
                os.environ[key] = value

    _LOADED_PATHS.add(env_path)
    return True
