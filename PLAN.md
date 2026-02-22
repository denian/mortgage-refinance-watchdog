# Mortgage Refinance Watchdog — Implementation Plan

## Overview

A Python-based service that fetches current 30-year fixed mortgage rates weekly,
performs refinance break-even analysis, alerts the user via email, and exposes a
web UI for viewing reports and managing settings.

---

## 1. Data Sources

### Primary: FRED API (`MORTGAGE30US`)

- **What**: Freddie Mac's Primary Mortgage Market Survey (PMMS), republished by
  the Federal Reserve Bank of St. Louis via FRED.
- **Series ID**: `MORTGAGE30US`
- **Update cadence**: Weekly, every Thursday ~10 AM Eastern.
- **Historical depth**: Since April 2, 1971.
- **API**: Free; requires a free API key from fred.stlouisfed.org.
- **Python library**: `fredapi` (wraps the FRED REST API cleanly).
- **Rate limit**: 120 requests/60 seconds — irrelevant for our use case.

### Fallback: Freddie Mac Direct Excel Download

- Freddie Mac publishes the same PMMS data as a downloadable Excel file at
  `https://www.freddiemac.com/pmms/docs/historicalweeklydata.xls`.
- No API key required. Parsed with `pandas.read_excel`.
- Used only if the FRED API key is missing or the FRED request fails.

### Why not other sources?

- **Bankrate** and **Mortgage News Daily** have no free programmatic API.
  Scraping is fragile and likely violates their ToS.
- **CFPB NMDB** is quarterly and research-focused — not suitable for live tracking.
- FRED is the gold standard for automated, reliable, free mortgage rate data.

---

## 2. Financial Mathematics

All calculations use the **`numpy-financial`** library (`npf`).

### Monthly Payment Formula

```
M = P × [r(1+r)^n] / [(1+r)^n − 1]
```

Where: `P` = principal, `r` = monthly rate (annual/12), `n` = months.

In code: `M = -npf.pmt(rate=annual_rate/12, nper=n_months, pv=principal)`

### Scenario A — Current Loan (no refinance)

- Balance: `$800,000` (configurable)
- Rate: `6.5%` (configurable)
- Remaining term: `30 years / 360 months` (configurable)
- Monthly payment computed from the above formula.
- Total remaining interest = `M × n − balance`

### Scenario B — Refinanced Loan

- Balance: same as Scenario A (assuming closing costs paid out-of-pocket)
- Rate: fetched from FRED
- Term: `30 years` (configurable, independent of current remaining term)
- Closing costs: `$6,000` (configurable; paid upfront, not rolled in)

### Break-Even Analysis

```
monthly_savings = payment_A − payment_B
break_even_months = closing_costs / monthly_savings
```

**Alert condition**: `break_even_months ≤ 24` (configurable threshold).

Edge cases handled:
- `monthly_savings ≤ 0`: new rate is higher — refinance is unfavorable, report explains why.
- `closing_costs == 0`: immediate savings (no-cost refi).

### Total Interest Comparison

- **Keep current loan**: `M_A × n_A − balance`
- **Refinance**: `M_B × n_B − balance + closing_costs`
- Net lifetime savings = difference between the two.

---

## 3. Project Structure

```
mortgage-monitor/
├── .env                        # Secrets: FRED API key, SMTP password
├── config.yaml                 # User settings (loan params, email, thresholds)
├── requirements.txt
├── main.py                     # CLI entry point: run the weekly check
├── src/
│   ├── __init__.py
│   ├── config.py               # Load/save config.yaml and .env
│   ├── rate_fetcher.py         # FRED API + fallback fetcher
│   ├── calculator.py           # All financial math (numpy-financial)
│   ├── report.py               # Console output + Markdown report generator
│   └── emailer.py              # SMTP email sender
├── web/
│   ├── app.py                  # FastAPI web application
│   ├── static/
│   │   └── style.css           # Minimal styling
│   └── templates/
│       ├── base.html           # Shared layout
│       ├── index.html          # Latest report view
│       └── settings.html       # Settings form
├── reports/
│   └── .gitkeep                # Generated reports stored here
└── systemd/
    ├── mortgage-monitor.service
    └── mortgage-monitor.timer
```

---

## 4. Module Details

### `src/config.py`

Loads and saves two configuration layers:

1. **`.env`** — secrets only (never committed to git):
   - `FRED_API_KEY`
   - `SMTP_PASSWORD`

2. **`config.yaml`** — all user-editable settings:
   ```yaml
   loan:
     balance: 800000
     rate: 0.065          # 6.5%
     remaining_months: 360
   refinance:
     new_term_months: 360
     closing_costs: 6000
     break_even_threshold_months: 24
   email:
     smtp_host: smtp.gmail.com
     smtp_port: 587
     smtp_user: you@gmail.com
     recipient: you@gmail.com
   ```

Provides `load_config() -> dict` and `save_config(data: dict)` functions.
The web UI writes to this same file when the user saves settings.

### `src/rate_fetcher.py`

```python
def fetch_current_rate() -> dict:
    """
    Returns:
        {
          "rate": 6.72,          # percent, e.g. 6.72
          "date": "2025-08-07",  # date of the observation
          "source": "FRED MORTGAGE30US"
        }
    Tries FRED first; falls back to Freddie Mac direct download.
    Raises RateFetchError if both sources fail.
    """
```

Also exposes `fetch_rate_history(months=12) -> pd.Series` for the report's
trend section.

### `src/calculator.py`

```python
def compute_scenario_a(balance, annual_rate, remaining_months) -> dict:
    """Monthly payment, total remaining interest."""

def compute_scenario_b(balance, new_annual_rate, new_term_months, closing_costs) -> dict:
    """Monthly payment, total cost including closing costs."""

def compute_break_even(scenario_a, scenario_b, closing_costs) -> dict:
    """
    Returns:
        {
          "monthly_savings": 412.50,
          "break_even_months": 14.5,
          "lifetime_savings": 148500.00,
          "should_alert": True,
          "reason": "Break-even in 14.5 months (threshold: 24)"
        }
    """
```

### `src/report.py`

Two outputs generated together:

1. **Console summary** — printed to stdout with clear section headers and the
   recommendation highlighted.

2. **Markdown file** — saved to `reports/report_YYYY-MM-DD.md` and also
   symlinked/copied to `reports/latest.md`. Contains:
   - Run date and data source date
   - Rate history note (52-week high/low)
   - Scenario comparison table (Markdown table, two columns)
   - Break-even analysis
   - Recommendation (ALERT or NOT YET)

Example Markdown table:

```markdown
| Metric                  | Current Loan    | Refinanced Loan  |
|-------------------------|-----------------|------------------|
| Balance                 | $800,000      | $800,000       |
| Interest Rate           | 6.5%           | 6.72%            |
| Term                    | 30 years        | 30 years         |
| Monthly Payment         | $9,111.34       | $9,558.21        |
| Total Interest (life)   | $1,800,082      | $2,040,956       |
| Closing Costs           | —               | $6,000           |
```

### `src/emailer.py`

- Uses Python's built-in `smtplib` with `STARTTLS` (port 587).
- Supports Gmail with App Password (documented in README).
- Sends a multipart email:
  - **Subject**: `[Mortgage Monitor] ALERT: Refinance now saves $412/mo` or
    `[Mortgage Monitor] Rates not low enough (break-even: 47 months)`
  - **Body**: HTML-rendered version of the Markdown report (using `markdown` library).
  - **Attachment**: `report.md` as a file attachment.

### `main.py`

Orchestrates the weekly check:

```python
def run():
    config = load_config()
    rate_data = fetch_current_rate()
    scenario_a = compute_scenario_a(...)
    scenario_b = compute_scenario_b(rate_data["rate"], ...)
    analysis = compute_break_even(scenario_a, scenario_b, closing_costs)
    print_console_report(rate_data, scenario_a, scenario_b, analysis)
    save_markdown_report(...)
    send_email(...)
```

Can also be called with `python main.py --dry-run` to skip email sending.

---

## 5. Web UI

**Framework**: FastAPI + Jinja2 templates + vanilla CSS (no heavy frontend framework).
Served on `http://localhost:8080` (configurable port).

### Routes

| Method | Path           | Description                                       |
|--------|----------------|---------------------------------------------------|
| GET    | `/`            | View latest report (rendered from `latest.md`)    |
| GET    | `/settings`    | Settings form                                     |
| POST   | `/settings`    | Save settings to `config.yaml`                    |
| POST   | `/run`         | Manually trigger a rate check (runs `main.run()`) |
| GET    | `/reports`     | List all historical reports                       |
| GET    | `/reports/{date}` | View a specific historical report              |

### Settings Form Fields

- Current loan balance (`$`)
- Current interest rate (`%`)
- Remaining term (months)
- Closing costs estimate (`$`)
- Break-even threshold (months, default 24)
- New term for refinance (months, default 360)
- Email recipient address
- SMTP host, port, username
- SMTP password (masked field, stored in `.env`)
- FRED API key (masked, stored in `.env`)

### UI Design

- Minimal: two pages (Report, Settings) with a top navbar.
- Report page renders the Markdown report as HTML using the `markdown` Python library.
- No JavaScript framework — plain HTML forms + a small amount of inline JS for the
  "Run Now" button (POST + show spinner).
- Mobile-friendly with a single-column layout.

---

## 6. Scheduling (Linux systemd timer)

Preferred over cron because it handles missed runs (e.g., server was off at 9 AM)
by running when it next comes online.

**`systemd/mortgage-monitor.service`**:
```ini
[Unit]
Description=Mortgage Refinance Watchdog
After=network.target

[Service]
Type=oneshot
User=%i
WorkingDirectory=/path/to/mortgage-monitor
ExecStart=/path/to/mortgage-monitor/.venv/bin/python main.py
EnvironmentFile=/path/to/mortgage-monitor/.env
```

**`systemd/mortgage-monitor.timer`**:
```ini
[Unit]
Description=Run Mortgage Refinance Watchdog every Monday at 9 AM Eastern

[Timer]
OnCalendar=Mon *-*-* 14:00:00 UTC   # 9 AM EST (UTC-5); adjust for EDT
Persistent=true                      # Run if missed (server was down)
AccuracySec=1min

[Install]
WantedBy=timers.target
```

Note on EST vs EDT: 9 AM EST = 14:00 UTC in winter, 9 AM EDT = 13:00 UTC in summer.
A small Python helper or a `TZ=America/New_York` environment variable with
`OnCalendar=Mon 09:00:00` handles this automatically in newer systemd versions.

A separate systemd service (`mortgage-monitor-web.service`) runs the FastAPI web
UI continuously as a long-running process.

---

## 7. Python Dependencies

```
fredapi>=0.5.1
numpy-financial>=1.0.0
pandas>=2.0.0
openpyxl>=3.1.0         # For Freddie Mac Excel fallback
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
jinja2>=3.1.0
python-multipart>=0.0.9  # FastAPI form parsing
markdown>=3.5.0           # Markdown → HTML for email/web
python-dotenv>=1.0.0
pyyaml>=6.0.1
requests>=2.31.0
```

No database required — config is stored in YAML, reports are stored as Markdown files.

---

## 8. Configuration & Secrets Management

- `.env` is never committed to git (add to `.gitignore`).
- `config.yaml` contains no secrets (safe to commit if desired).
- A `.env.example` file documents all required environment variables.
- On first run (if `config.yaml` is missing), the script prints setup instructions.

---

## 9. Implementation Order

1. **`src/config.py`** — Foundation; everything else depends on it.
2. **`src/rate_fetcher.py`** — Core data ingestion.
3. **`src/calculator.py`** — Core financial logic.
4. **`src/report.py`** — Console + Markdown output.
5. **`src/emailer.py`** — Email delivery.
6. **`main.py`** — Orchestrates 1–5; fully functional CLI tool.
7. **`web/app.py` + templates** — Web UI on top of the above.
8. **`systemd/`** — Scheduling configs.
9. **`requirements.txt`, `.env.example`, `README.md`** — Documentation.

---

## 10. Detailed Todo List

### Phase 1 — Project Scaffolding ✅

- [x] Create the full directory tree (`src/`, `web/templates/`, `web/static/`, `reports/`, `systemd/`)
- [x] Create `reports/.gitkeep` so the directory is tracked by git
- [x] Create `src/__init__.py` (empty)
- [x] Create `web/__init__.py` (empty)
- [x] Create `.gitignore` (exclude `.env`, `__pycache__`, `*.pyc`, `.venv/`, `reports/*.md`)
- [x] Create `requirements.txt` with all pinned dependencies
- [x] Create `.env.example` documenting `FRED_API_KEY` and `SMTP_PASSWORD`
- [x] Create `config.yaml` with all default values pre-filled (the user's actual loan data)
- [x] Create and activate a Python virtual environment (`.venv/`)
- [x] Install all dependencies from `requirements.txt`

---

### Phase 2 — Configuration Module (`src/config.py`) ✅

- [x] Implement `load_config() -> dict` — reads `config.yaml`, returns parsed dict
- [x] Implement `save_config(data: dict)` — writes dict back to `config.yaml`, preserving comments
- [x] Implement `load_secrets() -> dict` — reads `.env` via `python-dotenv`, returns key/value dict
- [x] Implement `save_secret(key: str, value: str)` — updates a single key in `.env` without clobbering others
- [x] Implement `get_full_config() -> dict` — merges `config.yaml` + `.env` into one config object for use by other modules
- [x] Handle missing `config.yaml` gracefully — create from defaults and print first-run setup message
- [x] Handle missing `.env` gracefully — warn the user which secrets are absent
- [x] Add config validation — raise clear errors for missing required fields, wrong types, out-of-range values (e.g., negative balance, rate > 1.0 instead of 0.065)
- [x] Write unit tests for load, save, and validation logic

---

### Phase 3 — Rate Fetcher (`src/rate_fetcher.py`) ✅

- [x] Define `RateFetchError` custom exception class
- [x] Implement `_fetch_from_fred(api_key: str) -> dict` — uses `fredapi` to get the latest `MORTGAGE30US` observation; returns `{rate, date, source}`
- [x] Implement `_fetch_from_freddie_mac() -> dict` — downloads the public Excel file from Freddie Mac, parses with `pandas`, returns same dict shape
- [x] Implement `fetch_current_rate() -> dict` — calls FRED first; on any failure (missing key, network error, stale data) falls back to Freddie Mac; raises `RateFetchError` if both fail
- [x] Implement `fetch_rate_history(months: int = 12) -> pd.Series` — returns a `DatetimeIndex`-indexed Series of the past N months of weekly rates for use in trend reporting
- [x] Add staleness check — if the most recent FRED observation is more than 10 days old, log a warning (may indicate FRED is behind)
- [x] Add error handling for network timeouts with a configurable timeout (default 15 s)
- [x] Write unit tests using mocked API responses (no real network calls in tests)

---

### Phase 4 — Financial Calculator (`src/calculator.py`) ✅

- [x] Implement `monthly_payment(principal, annual_rate, n_months) -> float` using `numpy_financial.pmt`; handle the 0% rate edge case
- [x] Implement `total_interest(principal, annual_rate, n_months) -> float` — total interest paid over full term
- [x] Implement `compute_scenario_a(balance, annual_rate, remaining_months) -> dict` — returns `{monthly_payment, total_interest, label}`
- [x] Implement `compute_scenario_b(balance, new_rate, new_term_months, closing_costs) -> dict` — returns `{monthly_payment, total_interest_plus_closing, label}`
- [x] Implement `compute_break_even(scenario_a, scenario_b, closing_costs, threshold_months) -> dict`:
  - Calculate `monthly_savings = payment_A − payment_B`
  - Handle `monthly_savings <= 0` (unfavorable: rate is higher or equal)
  - Calculate `break_even_months = closing_costs / monthly_savings`
  - Calculate `lifetime_savings = total_interest_A − (total_interest_B + closing_costs)`
  - Set `should_alert = break_even_months <= threshold_months`
  - Build `reason` string explaining the decision in plain English
- [x] Write unit tests for all functions with known-good values (manually verified with a mortgage calculator)
- [x] Add a `format_currency(value) -> str` and `format_percent(value) -> str` helper for consistent display throughout the app

---

### Phase 5 — Report Generator (`src/report.py`) ✅

- [x] Implement `build_report_data(rate_data, scenario_a, scenario_b, analysis, history) -> dict` — assembles all data into one structured dict for use by both console and Markdown renderers
- [x] Implement `print_console_report(report_data)`:
  - Print a separator header with the run date
  - Print data source and rate observation date
  - Print 52-week high/low from `history`
  - Print the scenario comparison as an aligned text table
  - Print break-even analysis with clear numbers
  - Print the recommendation in bold/highlighted text (`ALERT` or `NOT YET`)
- [x] Implement `render_markdown(report_data) -> str` — produces the full Markdown string:
  - H1 title with run date
  - Data source attribution
  - Rate trend section (52-week high/low)
  - Markdown comparison table (8 rows)
  - Break-even section with formula shown
  - Recommendation section with a clear verdict and explanation
- [x] Implement `save_report(markdown: str, run_date: str) -> Path`:
  - Save to `reports/report_YYYY-MM-DD.md`
  - Overwrite `reports/latest.md` with the same content (copy, not symlink, for portability)
  - Return the path to the timestamped file
- [x] Write a test that renders a report from fixture data and checks key strings are present in the output

---

### Phase 6 — Email Sender (`src/emailer.py`) ✅

- [x] Implement `build_subject(analysis: dict) -> str`:
  - Alert path: `[Mortgage Monitor] ALERT: Refinance saves $X/mo (break-even: N months)`
  - No-alert path: `[Mortgage Monitor] Rates not low enough yet (break-even: N months)`
- [x] Implement `markdown_to_html(md: str) -> str` — converts the Markdown report to styled HTML using the `markdown` library; wrap in a minimal `<html><body>` with inline CSS for readability
- [x] Implement `send_email(smtp_config: dict, subject: str, md_body: str, attachment_path: Path)`:
  - Build `MIMEMultipart("alternative")` with plain-text and HTML parts
  - Attach the `.md` file as `MIMEApplication`
  - Open SMTP connection with `STARTTLS` on port 587
  - Authenticate and send; close connection
- [x] Implement `test_smtp_connection(smtp_config: dict) -> bool` — used by the web UI's settings page to validate credentials before saving
- [x] Handle and log SMTP errors without crashing the main run (email failure should not stop the report from being saved)
- [x] Document Gmail App Password setup steps in a code comment (users need to enable 2FA + create an App Password)

---

### Phase 7 — Main Entry Point (`main.py`) ✅

- [x] Implement `run(dry_run: bool = False)`:
  1. `load config`
  2. `fetch_current_rate()` (with error handling — if fetch fails, exit with a clear error message)
  3. `fetch_rate_history(12)`
  4. `compute_scenario_a(...)` and `compute_scenario_b(...)`
  5. `compute_break_even(...)`
  6. `build_report_data(...)` and `print_console_report(...)`
  7. `save_report(render_markdown(...))`
  8. `send_email(...)` — skip if `dry_run=True`, log a note that email was skipped
- [x] Implement CLI argument parsing with `argparse`:
  - `--dry-run` / `-n`: skip email, print note to stdout
  - `--config PATH`: use a custom config file (default: `config.yaml`)
  - `--version`: print version string and exit
- [x] Add top-level try/except — on unhandled error, print a clean message to stderr and exit with code 1 (so systemd can detect failure)
- [x] Add basic logging setup (write to stdout; systemd captures it via journald)

---

### Phase 8 — Web UI (`web/app.py` + templates + static) ✅

#### `web/app.py` — FastAPI application

- [x] Create FastAPI app instance with title and description
- [x] Mount `web/static/` as a static files directory
- [x] Configure Jinja2 `TemplatesResponse` pointing to `web/templates/`
- [x] Implement `GET /` — load `reports/latest.md`, render to HTML, pass to `index.html` template; show placeholder message if no report exists yet
- [x] Implement `GET /reports` — list all `reports/report_*.md` files sorted by date descending; pass to `reports_list.html`
- [x] Implement `GET /reports/{date}` — load the specific report file, render to HTML, pass to `index.html`; return 404 if not found
- [x] Implement `GET /settings` — load current config (excluding secrets), populate `settings.html` form
- [x] Implement `POST /settings` — validate form data, call `save_config()` and `save_secret()` for masked fields, redirect to `GET /settings` with a success flash message
- [x] Implement `POST /run` — call `main.run()` in a background thread (so the HTTP response is not blocked); redirect to `GET /` with a "Check triggered" flash message
- [x] Add a simple flash message system (store one-time message in a response cookie)
- [x] Add error handler for 404 and 500 that renders a friendly HTML error page

#### `web/templates/base.html`

- [x] HTML5 doctype, charset, viewport meta tag
- [x] `<link>` to `style.css`
- [x] Top navbar with: app name ("Mortgage Monitor"), links to Report and Settings, and a "Run Now" button (POST form)
- [x] Flash message banner (shown only when message cookie is set)
- [x] `{% block content %}{% endblock %}` body area
- [x] Minimal footer with last-run date

#### `web/templates/index.html`

- [x] Extends `base.html`
- [x] Renders the report HTML inside a `<article>` element with good typography
- [x] Shows "No report yet — click Run Now to generate one" when `latest.md` is absent
- [x] Links to the full reports history list

#### `web/templates/reports_list.html`

- [x] Extends `base.html`
- [x] Table: Date | Recommendation | Break-even months | Link to view
- [x] Parse alert status from report filename or first few lines of the file

#### `web/templates/settings.html`

- [x] Extends `base.html`
- [x] Form with four fieldset groups:
  - **Current Loan**: balance, interest rate, remaining months
  - **Refinance Parameters**: new term, closing costs, break-even threshold
  - **Email**: recipient address, SMTP host, port, username, password (masked)
  - **API Keys**: FRED API key (masked), "Test Connection" button for SMTP
- [x] Client-side: mark required fields; show/hide password fields toggle
- [x] Submit button + cancel link

#### `web/static/style.css`

- [x] CSS reset / normalize basics
- [x] Navbar styles (horizontal, sticky)
- [x] Typography: readable font stack, line-height, max-width content area
- [x] Table styles (striped rows, responsive)
- [x] Form styles (label + input stacked layout, fieldset grouping)
- [x] Alert/recommendation box styles (green for ALERT, yellow for NOT YET)
- [x] Flash message banner style
- [x] Mobile breakpoint: collapse navbar, stack form fields

---

### Phase 9 — Systemd Configuration (`systemd/`) ✅

- [x] Write `mortgage-monitor.service`:
  - `Type=oneshot`
  - `WorkingDirectory` pointing to the install path (use placeholder `__INSTALL_DIR__`)
  - `ExecStart` pointing to `.venv/bin/python main.py`
  - `EnvironmentFile` pointing to `.env`
  - `StandardOutput=journal`, `StandardError=journal`
  - `After=network-online.target`
- [x] Write `mortgage-monitor.timer`:
  - `OnCalendar=Mon *-*-* 14:00:00 UTC` (9 AM EST / 13:00 UTC for EDT — note in comment)
  - Alternative using `TZ=America/New_York` + `OnCalendar=Mon 09:00` for automatic DST handling
  - `Persistent=true` so missed runs execute on next boot
  - `AccuracySec=1min`
  - `[Install] WantedBy=timers.target`
- [x] Write `mortgage-monitor-web.service`:
  - `Type=simple` (long-running)
  - `ExecStart=.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8080`
  - `Restart=on-failure`, `RestartSec=10`
  - `After=network.target`
  - `[Install] WantedBy=multi-user.target`
- [x] Write `install.sh` helper script that:
  - Substitutes `__INSTALL_DIR__` in the service files with the actual current directory
  - Copies files to `/etc/systemd/system/`
  - Runs `systemctl daemon-reload && systemctl enable --now mortgage-monitor.timer && systemctl enable --now mortgage-monitor-web.service`

---

### Phase 10 — Documentation & Final Wiring ✅

- [x] Write `README.md`:
  - Project overview and feature list
  - Prerequisites (Python 3.11+, Linux with systemd)
  - Step-by-step installation guide
  - How to get a free FRED API key (link + steps)
  - How to set up a Gmail App Password for SMTP
  - How to run manually (`python main.py`, `python main.py --dry-run`)
  - How to install and start the systemd services (`install.sh`)
  - How to access the web UI
  - Troubleshooting section (check `journalctl -u mortgage-monitor`, common SMTP errors)
- [x] Confirm `.gitignore` covers all secrets and generated files
- [x] Do a full end-to-end automated test:
  - [x] All 34 unit/integration tests pass (`pytest tests/ -v`)
  - [x] CLI `--version` and `--help` flags verified
  - [x] `--dry-run` mock run generates `reports/latest.md` correctly (test_main)
  - [x] All FastAPI routes smoke-tested with TestClient (/, /reports, /settings, 404)
  - [x] FRED API fallback verified (test_rate_fetcher)
  - [x] Web UI app imports cleanly with all 9 routes registered
  - [ ] Live SMTP email — requires real credentials (user must configure .env)
- [x] All phases marked complete in PLAN.md

---

## 11. Key Design Decisions & Trade-offs

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data source | FRED only (with Freddie Mac fallback) | Only free, stable, programmatic option |
| Update frequency | Weekly (matches FRED's cadence) | Daily data isn't available for free |
| Scheduler | systemd timer | More robust than cron; handles missed runs |
| Web framework | FastAPI + Jinja2 | Lightweight, modern, no JS build step needed |
| Config storage | YAML file + .env | Simple, human-readable, no database required |
| Email | smtplib STARTTLS | Built-in, no third-party email service dependency |
| Closing costs | Paid upfront (not rolled in) | Standard conservative assumption for break-even |
| Term for Scenario B | Configurable (defaults to 30 yr) | User may want 15-year refi option |
