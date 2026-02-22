import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"

_DEFAULTS = {
    "loan": {
        "balance": 800_000,
        "rate": 0.065,
        "remaining_months": 360,
    },
    "refinance": {
        "new_term_months": 360,
        "closing_costs": 6_000,
        "break_even_threshold_months": 24,
    },
    "email": {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "recipient": "",
    },
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        save_config(_DEFAULTS, path)
        print(
            f"[mortgage-monitor] Created default config at {path}. "
            "Please edit it before running."
        )
        return _deep_copy(_DEFAULTS)
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        data = {}
    _validate_config(data)
    return data


def save_config(data: dict, path: Path = CONFIG_PATH) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def load_secrets(env_path: Path = ENV_PATH) -> dict:
    missing = []
    if not env_path.exists():
        missing = ["FRED_API_KEY", "SMTP_PASSWORD"]
    else:
        load_dotenv(env_path, override=True)
        for key in ("FRED_API_KEY", "SMTP_PASSWORD"):
            if not os.getenv(key):
                missing.append(key)
    if missing:
        print(
            f"[mortgage-monitor] WARNING: missing secrets in {env_path}: "
            + ", ".join(missing)
            + f". Copy .env.example to {env_path} and fill in the values."
        )
    return {
        "FRED_API_KEY": os.getenv("FRED_API_KEY", ""),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
    }


def save_secret(key: str, value: str, env_path: Path = ENV_PATH) -> None:
    lines: list[str] = []
    if env_path.exists():
        with open(env_path) as f:
            lines = f.readlines()
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    new_line = f"{key}={value}\n"
    replaced = False
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)
    with open(env_path, "w") as f:
        f.writelines(lines)
    load_dotenv(env_path, override=True)


def get_full_config(config_path: Path = CONFIG_PATH, env_path: Path = ENV_PATH) -> dict:
    cfg = load_config(config_path)
    secrets = load_secrets(env_path)
    cfg["secrets"] = secrets
    return cfg


def _validate_config(data: dict) -> None:
    errors = []

    loan = data.get("loan", {})
    balance = loan.get("balance")
    if balance is None or not isinstance(balance, (int, float)) or balance <= 0:
        errors.append("loan.balance must be a positive number")
    rate = loan.get("rate")
    if rate is None or not isinstance(rate, (int, float)) or not (0 < rate < 1):
        errors.append("loan.rate must be a decimal between 0 and 1 (e.g. 0.065 for 6.5%)")
    remaining = loan.get("remaining_months")
    if remaining is None or not isinstance(remaining, int) or remaining <= 0:
        errors.append("loan.remaining_months must be a positive integer")

    refi = data.get("refinance", {})
    new_term = refi.get("new_term_months")
    if new_term is None or not isinstance(new_term, int) or new_term <= 0:
        errors.append("refinance.new_term_months must be a positive integer")
    closing = refi.get("closing_costs")
    if closing is None or not isinstance(closing, (int, float)) or closing < 0:
        errors.append("refinance.closing_costs must be a non-negative number")
    threshold = refi.get("break_even_threshold_months")
    if threshold is None or not isinstance(threshold, int) or threshold <= 0:
        errors.append("refinance.break_even_threshold_months must be a positive integer")

    email = data.get("email", {})
    port = email.get("smtp_port")
    if port is not None and (not isinstance(port, int) or port <= 0):
        errors.append("email.smtp_port must be a positive integer")

    if errors:
        raise ValueError("Invalid config.yaml:\n  - " + "\n  - ".join(errors))


def _deep_copy(d: Any) -> Any:
    import copy
    return copy.deepcopy(d)
