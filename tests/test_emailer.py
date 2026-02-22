from src.emailer import build_subject, markdown_to_html


def test_build_subject_alert():
    analysis = {"should_alert": True, "monthly_savings": 450.0, "break_even_months": 13.3}
    subject = build_subject(analysis)
    assert "ALERT" in subject
    assert "$450.00" in subject
    assert "13" in subject


def test_build_subject_no_alert():
    analysis = {"should_alert": False, "monthly_savings": 50.0, "break_even_months": 120.0}
    subject = build_subject(analysis)
    assert "ALERT" not in subject
    assert "120" in subject


def test_build_subject_no_savings():
    analysis = {"should_alert": False, "monthly_savings": -100.0, "break_even_months": float("inf")}
    subject = build_subject(analysis)
    assert "no monthly savings" in subject


def test_markdown_to_html_contains_table():
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    html = markdown_to_html(md)
    assert "<table>" in html
    assert "<td>" in html


def test_markdown_to_html_wrapped():
    html = markdown_to_html("# Hello")
    assert "<!DOCTYPE html>" in html
    assert "<h1>" in html
    assert "<body>" in html
