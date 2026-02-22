import pytest
import yaml
from pathlib import Path
from src.config import load_config, save_config, save_secret, _validate_config


def test_load_config_creates_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    cfg = load_config(path)
    assert cfg["loan"]["balance"] == 800_000
    assert path.exists()


def test_save_and_reload(tmp_path):
    path = tmp_path / "config.yaml"
    data = {
        "loan": {"balance": 500_000, "rate": 0.05, "remaining_months": 240},
        "refinance": {"new_term_months": 360, "closing_costs": 5000, "break_even_threshold_months": 24},
        "email": {"smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_user": "a@b.com", "recipient": "a@b.com"},
    }
    save_config(data, path)
    loaded = load_config(path)
    assert loaded["loan"]["balance"] == 500_000
    assert loaded["loan"]["rate"] == 0.05


def test_validate_config_bad_rate():
    with pytest.raises(ValueError, match="loan.rate"):
        _validate_config({"loan": {"balance": 500_000, "rate": 6.5, "remaining_months": 360},
                          "refinance": {"new_term_months": 360, "closing_costs": 5000, "break_even_threshold_months": 24},
                          "email": {}})


def test_validate_config_negative_balance():
    with pytest.raises(ValueError, match="loan.balance"):
        _validate_config({"loan": {"balance": -1, "rate": 0.05, "remaining_months": 360},
                          "refinance": {"new_term_months": 360, "closing_costs": 5000, "break_even_threshold_months": 24},
                          "email": {}})


def test_save_secret_creates_env(tmp_path):
    env = tmp_path / ".env"
    save_secret("FRED_API_KEY", "abc123", env)
    assert "FRED_API_KEY=abc123" in env.read_text()


def test_save_secret_updates_existing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FRED_API_KEY=old\nSMTP_PASSWORD=pass\n")
    save_secret("FRED_API_KEY", "new_key", env)
    text = env.read_text()
    assert "FRED_API_KEY=new_key" in text
    assert "old" not in text
    assert "SMTP_PASSWORD=pass" in text
