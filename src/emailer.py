import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import markdown as md_lib

from .calculator import format_currency

_HTML_WRAPPER = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Georgia, serif; max-width: 800px; margin: 40px auto; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
  th {{ background: #f4f4f4; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  pre {{ background: #f6f6f6; padding: 12px; border-radius: 4px; overflow-x: auto; }}
  code {{ font-family: monospace; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: 8px; }}
  h2 {{ border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 2em; }}
  h3.alert {{ color: #1a7f37; }}
  h3.not-yet {{ color: #9a6700; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def build_subject(analysis: dict) -> str:
    if analysis["should_alert"]:
        savings = format_currency(analysis["monthly_savings"])
        be = analysis["break_even_months"]
        return (
            f"[Mortgage Monitor] ALERT: Refinance saves {savings}/mo "
            f"(break-even: {be:.0f} months)"
        )
    be = analysis["break_even_months"]
    if be == float("inf"):
        return "[Mortgage Monitor] Rates not low enough yet (no monthly savings)"
    return (
        f"[Mortgage Monitor] Rates not low enough yet "
        f"(break-even: {be:.0f} months)"
    )


def markdown_to_html(md_text: str) -> str:
    body = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])
    return _HTML_WRAPPER.format(body=body)


def send_email(
    smtp_config: dict,
    subject: str,
    md_body: str,
    attachment_path: Path | None = None,
) -> None:
    """
    smtp_config keys: smtp_host, smtp_port, smtp_user, smtp_password, recipient
    Raises smtplib.SMTPException on failure (caller should catch and log).
    """
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = smtp_config["smtp_user"]
    msg["To"] = smtp_config["recipient"]

    html_body = markdown_to_html(md_body)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(md_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    if attachment_path and Path(attachment_path).exists():
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
        part["Content-Disposition"] = (
            f'attachment; filename="{Path(attachment_path).name}"'
        )
        msg.attach(part)

    with smtplib.SMTP(smtp_config["smtp_host"], smtp_config["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_config["smtp_user"], smtp_config["smtp_password"])
        server.sendmail(
            smtp_config["smtp_user"],
            smtp_config["recipient"],
            msg.as_bytes(),
        )


def test_smtp_connection(smtp_config: dict) -> tuple[bool, str]:
    """
    Returns (success, message). Used by the web UI settings page.
    """
    try:
        with smtplib.SMTP(smtp_config["smtp_host"], smtp_config["smtp_port"], timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_config["smtp_user"], smtp_config["smtp_password"])
        return True, "Connection successful"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed — check username and password (Gmail: use an App Password)"
    except smtplib.SMTPConnectError as e:
        return False, f"Could not connect to {smtp_config['smtp_host']}:{smtp_config['smtp_port']} — {e}"
    except Exception as e:
        return False, str(e)
