import threading
from pathlib import Path
from typing import Annotated

import markdown as md_lib
from fastapi import FastAPI, Form, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import get_full_config, save_config, save_secret, load_config, ENV_PATH
from src.emailer import test_smtp_connection

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Mortgage Monitor", description="Mortgage Refinance Watchdog")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_run_lock = threading.Lock()


def _flash(response: RedirectResponse, message: str, kind: str = "info") -> None:
    response.set_cookie("flash_msg", message, max_age=10, httponly=True)
    response.set_cookie("flash_kind", kind, max_age=10, httponly=True)


def _get_flash(request: Request) -> dict | None:
    msg = request.cookies.get("flash_msg")
    kind = request.cookies.get("flash_kind", "info")
    if msg:
        return {"message": msg, "kind": kind}
    return None


def _clear_flash(response) -> None:
    response.delete_cookie("flash_msg")
    response.delete_cookie("flash_kind")


def _render_md_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return md_lib.markdown(text, extensions=["tables", "fenced_code"])


def _list_reports() -> list[dict]:
    reports = []
    for f in sorted(REPORTS_DIR.glob("report_*.md"), reverse=True):
        date_str = f.stem.replace("report_", "")
        content = f.read_text(encoding="utf-8")
        alert = "ALERT" in content and "## Recommendation" in content and "✅" in content
        reports.append({"filename": f.name, "date": date_str, "alert": alert})
    return reports


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    latest = REPORTS_DIR / "latest.md"
    report_html = _render_md_file(latest) if latest.exists() else None
    flash = _get_flash(request)
    response = templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "report_html": report_html,
            "flash": flash,
            "reports": _list_reports()[:5],
        },
    )
    _clear_flash(response)
    return response


@app.get("/reports", response_class=HTMLResponse)
async def reports_list(request: Request):
    flash = _get_flash(request)
    response = templates.TemplateResponse(
        "reports_list.html",
        {"request": request, "reports": _list_reports(), "flash": flash},
    )
    _clear_flash(response)
    return response


@app.get("/reports/{date_str}", response_class=HTMLResponse)
async def view_report(request: Request, date_str: str):
    path = REPORTS_DIR / f"report_{date_str}.md"
    if not path.exists():
        return HTMLResponse("<h1>Report not found</h1>", status_code=404)
    report_html = _render_md_file(path)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "report_html": report_html,
            "flash": None,
            "reports": _list_reports()[:5],
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request):
    cfg = get_full_config()
    flash = _get_flash(request)
    response = templates.TemplateResponse(
        "settings.html",
        {"request": request, "cfg": cfg, "flash": flash},
    )
    _clear_flash(response)
    return response


@app.post("/settings")
async def settings_post(
    request: Request,
    balance: Annotated[float, Form()],
    rate: Annotated[float, Form()],
    remaining_months: Annotated[int, Form()],
    new_term_months: Annotated[int, Form()],
    closing_costs: Annotated[float, Form()],
    break_even_threshold_months: Annotated[int, Form()],
    recipient: Annotated[str, Form()],
    smtp_host: Annotated[str, Form()],
    smtp_port: Annotated[int, Form()],
    smtp_user: Annotated[str, Form()],
    smtp_password: Annotated[str, Form()] = "",
    fred_api_key: Annotated[str, Form()] = "",
):
    cfg = load_config()
    cfg["loan"]["balance"] = balance
    cfg["loan"]["rate"] = rate / 100 if rate > 1 else rate
    cfg["loan"]["remaining_months"] = remaining_months
    cfg["refinance"]["new_term_months"] = new_term_months
    cfg["refinance"]["closing_costs"] = closing_costs
    cfg["refinance"]["break_even_threshold_months"] = break_even_threshold_months
    cfg["email"]["recipient"] = recipient
    cfg["email"]["smtp_host"] = smtp_host
    cfg["email"]["smtp_port"] = smtp_port
    cfg["email"]["smtp_user"] = smtp_user
    save_config(cfg)
    if smtp_password:
        save_secret("SMTP_PASSWORD", smtp_password, ENV_PATH)
    if fred_api_key:
        save_secret("FRED_API_KEY", fred_api_key, ENV_PATH)

    resp = RedirectResponse("/settings", status_code=303)
    _flash(resp, "Settings saved successfully.", "success")
    return resp


@app.post("/test-smtp")
async def test_smtp(
    smtp_host: Annotated[str, Form()],
    smtp_port: Annotated[int, Form()],
    smtp_user: Annotated[str, Form()],
    smtp_password: Annotated[str, Form()] = "",
):
    from src.config import load_secrets
    if not smtp_password:
        smtp_password = load_secrets().get("SMTP_PASSWORD", "")
    ok, msg = test_smtp_connection({
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
    })
    kind = "success" if ok else "error"
    resp = RedirectResponse("/settings", status_code=303)
    _flash(resp, f"SMTP test: {msg}", kind)
    return resp


def _do_run():
    import main as m
    try:
        m.run(dry_run=False)
    except SystemExit:
        pass
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Background run failed: %s", exc)


@app.post("/run")
async def trigger_run(background_tasks: BackgroundTasks):
    if _run_lock.locked():
        resp = RedirectResponse("/", status_code=303)
        _flash(resp, "A check is already in progress.", "warning")
        return resp
    background_tasks.add_task(_run_with_lock)
    resp = RedirectResponse("/", status_code=303)
    _flash(resp, "Rate check started in the background. Refresh in a moment.", "info")
    return resp


def _run_with_lock():
    with _run_lock:
        _do_run()


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": 404, "message": "Page not found"},
        status_code=404,
    )


@app.exception_handler(500)
async def server_error(request: Request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": 500, "message": "Internal server error"},
        status_code=500,
    )
