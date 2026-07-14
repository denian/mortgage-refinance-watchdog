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


def _base_config(**extra):
    cfg = {
        "loan": {"balance": 500_000, "rate": 0.05, "remaining_months": 240},
        "refinance": {"new_term_months": 360, "closing_costs": 5000, "break_even_threshold_months": 24},
        "email": {},
    }
    cfg.update(extra)
    return cfg


def test_validate_config_principal_payments_ok():
    cfg = _base_config(principal_payments=[{"date": "2026-03-09", "amount": 25_000}])
    cfg["loan"]["first_payment_date"] = "2026-04-01"
    _validate_config(cfg)  # should not raise


def test_validate_config_principal_payments_require_first_payment_date():
    cfg = _base_config(principal_payments=[{"date": "2026-03-09", "amount": 25_000}])
    with pytest.raises(ValueError, match="first_payment_date is required"):
        _validate_config(cfg)


def test_validate_config_bad_principal_payment_amount():
    cfg = _base_config(principal_payments=[{"date": "2026-03-09", "amount": -5}])
    cfg["loan"]["first_payment_date"] = "2026-04-01"
    with pytest.raises(ValueError, match="amount"):
        _validate_config(cfg)


def test_load_config_parses_dates(tmp_path):
    path = tmp_path / "config.yaml"
    data = _base_config(principal_payments=[{"date": "2026-03-09", "amount": 25_000}])
    data["loan"]["first_payment_date"] = "2026-04-01"
    save_config(data, path)
    loaded = load_config(path)
    import datetime
    assert loaded["loan"]["first_payment_date"] == datetime.date(2026, 4, 1)
    assert loaded["principal_payments"][0]["date"] == datetime.date(2026, 3, 9)


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
