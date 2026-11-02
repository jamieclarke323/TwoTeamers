from html.parser import HTMLParser

import pytest

from test_offline import offline_app, offline_client


class PolicyParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_heading = False
        self.headings = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self.in_heading = True
        if tag == "a":
            self.links.append(dict(attrs).get("href"))

    def handle_endtag(self, tag):
        if tag == "h2":
            self.in_heading = False

    def handle_data(self, data):
        if self.in_heading:
            self.headings.append(data)


def test_policy_is_public_and_contains_all_sections(offline_client):
    response = offline_client.get("/privacy-policy")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    parser = PolicyParser()
    parser.feed(page.split('<article class="privacy-policy">', 1)[1].split("</article>", 1)[0])
    assert [heading.split(".", 1)[0] for heading in parser.headings] == [
        str(number) for number in range(1, 16)
    ]
    assert "<title>Privacy Policy | Two Teamers</title>" in page
    assert "Last updated: November 2026" in page
    assert "We use Google Analytics" in page
    assert "Rejecting analytics does not affect gameplay" in page
    assert "180 days" in page
    assert "https://policies.google.com/privacy" in parser.links
    assert "Operator: Jamie Clarke" in page
    assert "unique push subscription identifier" in page
    assert "Daily Game notifications" in page
    assert "My Team notifications" in page
    assert "hashed subscription endpoint" in page
    assert "The expiry of the cookie does not automatically delete" in page
    assert "mailto:twoteamerssupport@gmail.com" in parser.links
    assert "https://ico.org.uk/" in parser.links


@pytest.mark.parametrize("path", [
    "/", "/login", "/signup", "/teams", "/leagues", "/report",
    "/privacy-policy", "/quiz/offline-test",
])
def test_shared_footer_links_to_policy(offline_client, path):
    response = offline_client.get(path)
    assert response.status_code == 200
    footer = response.get_data(as_text=True).split("<footer>", 1)[1].split("</footer>", 1)[0]
    assert 'class="footer-link" href="/privacy-policy">Privacy Policy</a>' in footer


@pytest.mark.parametrize("path", ["/", "/login", "/privacy-policy", "/quiz/offline-test"])
def test_shared_online_header_blocks_google_until_consent(offline_client, path):
    response = offline_client.get(path)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    head = page.split("<head>", 1)[1].split("</head>", 1)[0]
    assert "googletagmanager.com" not in page
    assert 'src="/static/js/analytics-consent.js"' in head
    assert 'id="analytics-accept">Accept</button>' in page
    assert 'id="analytics-reject">Reject</button>' in page
    assert (
        "We may use third party analytics to provide vital support to the maintenance "
        "of Two Teamers website. Google receives website usage and device information. "
        "You can change your choice using Cookie settings."
    ) in page
    assert 'id="analytics-settings"' in page


def test_policy_link_is_present_for_accounts_and_offline_downloads(offline_client):
    response = offline_client.post("/signup", data={
        "email": "privacy@example.com", "password": "football123", "supported_team": "Neutral",
    })
    assert response.status_code == 302
    for path in ("/profile", "/privacy-policy"):
        page = offline_client.get(path).get_data(as_text=True)
        assert 'class="footer-link" href="/privacy-policy">Privacy Policy</a>' in page
    downloaded = offline_client.post("/quiz/offline-test/offline-package").get_json()
    assert 'class="footer-link" href="/privacy-policy">Privacy Policy</a>' in downloaded["html"]
    assert "googletagmanager.com" not in downloaded["html"]
    assert "gtag('config'" not in downloaded["html"]
    assert "analytics-consent.js" not in downloaded["html"]
