from urllib.parse import quote


def test_quiz_page_links_to_report_page(client, app):
    quiz = app.config["QUIZZES"][0]
    page = client.get(f"/quiz/{quiz.quiz_id}").data
    assert b'href="/report"' in page
    assert b"Spotted an error? Contact" in page


def test_report_page_lists_error_types(client):
    page = client.get("/report").data
    for option in (b"App functionality", b"Stats error", b"Valid answer not listed/Invalid answer listed", b"Other"):
        assert option in page


def test_report_redirects_to_prefilled_email(client):
    response = client.get("/report/send", query_string={"type": "Stats error"})
    assert response.status_code == 302
    assert response.headers["Location"] == "mailto:twoteamerssupport@gmail.com?subject=Stats%20error"
    slash = client.get("/report/send", query_string={"type": "Valid answer not listed/Invalid answer listed"})
    assert slash.headers["Location"].endswith(quote("Valid answer not listed/Invalid answer listed"))


def test_report_rejects_unknown_type(client):
    response = client.get("/report/send", query_string={"type": "Hello\r\nBcc: x@y.com"})
    assert response.headers["Location"].endswith("/report")
