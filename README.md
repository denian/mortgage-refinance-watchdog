# Mortgage Refinance Watchdog

A Python service that checks current 30-year fixed mortgage rates every Monday at
9 AM Eastern, calculates whether refinancing your loan would break even within your
target window, and emails you a full report either way.

## Features

- Fetches rates from the **FRED API** (`MORTGAGE30US` — Freddie Mac PMMS), with
  automatic fallback to a direct Freddie Mac file download
- Financial math via **numpy-financial** (standard amortization, break-even analysis,
  lifetime savings)
- Prints a formatted report to the console and saves a Markdown file
- Emails an HTML report with the Markdown file attached
- **Web UI** (FastAPI) to view all reports and manage settings at
  `http://your-server:8080`
- Automated weekly schedule via **systemd timer** (handles missed runs if the server
  was offline)

---

## Prerequisites

- Python 3.11+
- Linux with systemd (for automated scheduling; manual runs work on any OS)
- A free [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html)
- An SMTP account for email delivery (Gmail instructions below)

---

## Installation

```bash
# 1. Clone and enter the project
git clone <repo-url> mortgage-monitor
cd mortgage-monitor

# 2. Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Copy the secrets template and fill in your values
cp .env.example .env
nano .env          # set FRED_API_KEY and SMTP_PASSWORD
```

### Get a FRED API Key

1. Go to https://fred.stlouisfed.org/docs/api/api_key.html
2. Click **Request API Key**
3. Fill in your name, email, and brief description ("personal mortgage tracker")
4. Copy the key and paste it into `.env` as `FRED_API_KEY=...`

The key is free and instant. No credit card required.

### Set up Gmail SMTP (App Password)

If you use Gmail, standard passwords won't work — you need an **App Password**:

1. Enable 2-Step Verification on your Google account at
   [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Select **Mail** and your device, then click **Generate**
4. Copy the 16-character password into `.env` as `SMTP_PASSWORD=...`

For other providers, use your regular SMTP password.

---

## Configuration

Edit `config.yaml` to set your loan details and email address:

```yaml
loan:
  balance: 800000        # Current outstanding balance ($)
  rate: 0.065            # Current interest rate as a decimal (6.5% → 0.065)
  remaining_months: 360  # Months left on the loan

refinance:
  new_term_months: 360              # Term for the hypothetical new loan
  closing_costs: 6000               # Estimated closing costs ($)
  break_even_threshold_months: 24   # Alert if break-even ≤ this many months

email:
  smtp_host: smtp.gmail.com
  smtp_port: 587
  smtp_user: you@gmail.com
  recipient: you@gmail.com
```

You can also edit all settings through the web UI at `/settings`.

---

## Running Manually

```bash
# Full run (fetches rate, prints report, saves report.md, sends email)
.venv/bin/python main.py

# Dry run (skip email)
.venv/bin/python main.py --dry-run

# Custom config file
.venv/bin/python main.py --config /path/to/my-config.yaml
```

---

## Starting the Web UI

```bash
.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8080
```

Then open http://your-server:8080 in a browser.

---

## Setting Up Automated Weekly Runs

### macOS (launchd)

```bash
bash launchd/install.sh
```

This will:
1. Write two `~/Library/LaunchAgents/` plist files, substituting your install path
2. Load `com.mortgage-monitor.run` — runs `main.py` every Monday at 9 AM **local time**
   (ensure your Mac's timezone is set to America/New_York in System Settings → General → Date & Time)
3. Load `com.mortgage-monitor.web` — keeps the web UI running, restarts on crash

```bash
# Trigger the weekly check manually right now
launchctl start com.mortgage-monitor.run

# Watch logs
tail -f logs/run.log
tail -f logs/web.log

# Uninstall
launchctl unload ~/Library/LaunchAgents/com.mortgage-monitor.run.plist
launchctl unload ~/Library/LaunchAgents/com.mortgage-monitor.web.plist
```

### Linux (systemd)

Run the install script as root or with sudo:

```bash
sudo bash systemd/install.sh
```

This will:
1. Copy the three unit files to `/etc/systemd/system/`, substituting your
   install path and username
2. Enable and start `mortgage-monitor.timer` (runs `main.py` every Monday 9 AM Eastern)
3. Enable and start `mortgage-monitor-web.service` (keeps the web UI running)

### Check status

```bash
# See when the next run is scheduled
systemctl status mortgage-monitor.timer

# See the web UI service status
systemctl status mortgage-monitor-web.service

# Watch live logs from the weekly check
journalctl -u mortgage-monitor -f

# Watch live logs from the web UI
journalctl -u mortgage-monitor-web -f
```

### Manual systemd trigger

```bash
systemctl start mortgage-monitor.service
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `RateFetchError: All rate sources failed` | Check your `FRED_API_KEY` in `.env`; verify network access |
| `SMTPAuthenticationError` | For Gmail, use an App Password (see above); check `smtp_user` matches the account |
| `SMTPConnectError` | Verify `smtp_host` and `smtp_port`; check firewall rules for port 587 |
| Web UI shows "No report yet" | Click **Run Now** or run `python main.py --dry-run` first |
| Timer not running | Run `systemctl daemon-reload` then `systemctl enable --now mortgage-monitor.timer` |
| Rate data is stale | FRED publishes every Thursday ~10 AM ET; the warning fires if data is >10 days old |

---

## Project Structure

```
mortgage-monitor/
├── .env                        # Secrets (not committed)
├── config.yaml                 # User settings
├── requirements.txt
├── main.py                     # CLI entry point
├── src/
│   ├── config.py               # Config loading/saving
│   ├── rate_fetcher.py         # FRED API + fallback
│   ├── calculator.py           # Financial math (numpy-financial)
│   ├── report.py               # Console + Markdown report
│   └── emailer.py              # SMTP email sender
├── web/
│   ├── app.py                  # FastAPI web application
│   ├── static/style.css
│   └── templates/              # Jinja2 HTML templates
├── reports/                    # Generated reports (report_YYYY-MM-DD.md + latest.md)
├── systemd/                    # systemd unit files + install.sh
└── tests/                      # pytest test suite
```

---

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v
```
