import argparse
import logging
import sys
from pathlib import Path

from src.config import get_full_config
from src.rate_fetcher import fetch_current_rate, fetch_rate_history, RateFetchError
from src.calculator import compute_scenario_a, compute_scenario_b, compute_break_even
from src.report import build_report_data, print_console_report, render_markdown, save_report
from src.emailer import build_subject, send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

__version__ = "1.0.0"


def run(dry_run: bool = False, config_path: Path | None = None) -> None:

    cfg = get_full_config(config_path) if config_path else get_full_config()
    loan = cfg["loan"]
    refi = cfg["refinance"]
    email_cfg = cfg["email"]
    secrets = cfg["secrets"]

    log.info("Fetching current mortgage rate...")
    try:
        rate_data = fetch_current_rate(api_key=secrets.get("FRED_API_KEY", ""))
    except RateFetchError as exc:
        log.error("Failed to fetch mortgage rate: %s", exc)
        sys.exit(1)

    log.info("Rate: %.2f%% (as of %s, source: %s)", rate_data["rate"], rate_data["date"], rate_data["source"])

    log.info("Fetching rate history...")
    try:
        history = fetch_rate_history(api_key=secrets.get("FRED_API_KEY", ""), months=52)
    except RateFetchError:
        import pandas as pd
        history = pd.Series(dtype=float)
        log.warning("Could not fetch rate history; 52-week range will be omitted.")

    scenario_a = compute_scenario_a(
        balance=loan["balance"],
        annual_rate=loan["rate"],
        remaining_months=loan["remaining_months"],
    )
    scenario_b = compute_scenario_b(
        balance=loan["balance"],
        new_annual_rate=rate_data["rate"] / 100,
        new_term_months=refi["new_term_months"],
        closing_costs=refi["closing_costs"],
    )
    analysis = compute_break_even(
        scenario_a=scenario_a,
        scenario_b=scenario_b,
        closing_costs=refi["closing_costs"],
        threshold_months=refi["break_even_threshold_months"],
    )

    report_data = build_report_data(rate_data, scenario_a, scenario_b, analysis, history)
    print_console_report(report_data)

    md = render_markdown(report_data)
    report_path = save_report(md)
    log.info("Report saved to %s", report_path)

    if dry_run:
        log.info("--dry-run: skipping email.")
        return

    if not email_cfg.get("recipient") or not email_cfg.get("smtp_user"):
        log.warning("Email not configured (recipient or smtp_user is empty). Skipping.")
        return

    smtp_config = {
        "smtp_host": email_cfg["smtp_host"],
        "smtp_port": email_cfg["smtp_port"],
        "smtp_user": email_cfg["smtp_user"],
        "smtp_password": secrets.get("SMTP_PASSWORD", ""),
        "recipient": email_cfg["recipient"],
    }
    subject = build_subject(analysis)
    log.info("Sending email to %s...", email_cfg["recipient"])
    try:
        send_email(smtp_config, subject, md, attachment_path=report_path)
        log.info("Email sent successfully.")
    except Exception as exc:
        log.error("Failed to send email: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mortgage Refinance Watchdog — weekly rate check and alert."
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Fetch rates and generate report, but skip sending email.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        default=None,
        help="Path to a custom config.yaml (default: config.yaml in project root).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mortgage-monitor {__version__}",
    )
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, config_path=args.config)
    except SystemExit:
        raise
    except Exception as exc:
        log.error("Unexpected error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
