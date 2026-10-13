"""Browser test of the whole product, against servers that are already running (./dev.sh).

    backend/.venv/bin/pip install -r scripts/requirements-e2e.txt
    backend/.venv/bin/python scripts/e2e.py --web http://localhost:3000

It uses the Chrome installed on the machine, registers a new account, and walks through
streaming, stop, history, the usage limit and the admin page. Screenshots go to docs/.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

DOCS = Path(__file__).resolve().parents[1] / "docs"
ADMIN = ("admin@example.com", "admin-demo-1")


def step(text: str) -> None:
    print(f"  ok  {text}", flush=True)


def sign_in(page: Page, web: str, email: str, password: str) -> None:
    page.goto(f"{web}/login")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", password)
    page.click("button:has-text('Sign in')")
    page.wait_for_url(f"{web}/app")


def run(web: str, headed: bool) -> None:
    email = f"e2e-{int(time.time())}@example.com"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not headed)
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()

        page.goto(f"{web}/app")
        page.wait_for_url(f"{web}/login")
        step("a signed-out visitor is sent from /app to /login")

        page.goto(f"{web}/")
        expect(page.get_by_text("20 messages per day")).to_be_visible()
        page.screenshot(path=DOCS / "landing.png")
        step("the landing page shows the plan limits served by the API")

        page.goto(f"{web}/register")
        page.fill("input[name=name]", "Sara")
        page.fill("input[name=email]", email)
        page.fill("input[name=password]", "correct-horse-1")
        page.click("button:has-text('Create account')")
        page.wait_for_url(f"{web}/app")
        expect(page.get_by_test_id("usage-meter")).to_contain_text("0 / 20 today")
        step(f"registered {email} and landed in the app with a full allowance")

        # 1. A streamed answer: the text must grow while the request is still open.
        page.click("text=Write a product description for a hand-thrown ceramic mug")
        answer = page.get_by_test_id("message-assistant").last
        expect(answer).to_have_attribute("data-status", "streaming")
        page.wait_for_function(
            "document.querySelector('[data-testid=message-assistant]').innerText.length > 40")
        early = len(answer.inner_text())
        assert answer.get_attribute("data-status") == "streaming", "the answer arrived in one piece"
        page.screenshot(path=DOCS / "chat-streaming.png")
        expect(answer).to_have_attribute("data-status", "complete", timeout=15_000)
        final = len(answer.inner_text())
        assert final > early * 2, (early, final)
        expect(page.get_by_test_id("usage-meter")).to_contain_text("1 / 20 today")
        step(f"the answer streamed ({early} characters visible mid-stream, {final} at the end)")

        # 2. Stop: the partial answer stays, on the screen and on the server.
        page.fill("[data-testid=composer]", "Reply to a customer whose parcel is three days late")
        page.click("[data-testid=send]")
        page.wait_for_function(
            "[...document.querySelectorAll('[data-testid=message-assistant]')].at(-1).innerText.length > 30")
        page.click("[data-testid=stop]")
        expect(answer).to_have_attribute("data-status", "stopped")
        partial = answer.inner_text().split("\n")[0]
        expect(page.get_by_test_id("usage-meter")).to_contain_text("2 / 20 today")
        page.reload()
        expect(page.get_by_test_id("conversation-item")).to_have_count(1)
        page.get_by_test_id("conversation-item").first.locator("button").first.click()
        expect(page.get_by_test_id("message-assistant")).to_have_count(2)
        saved = page.get_by_test_id("message-assistant").last
        expect(saved).to_have_attribute("data-status", "stopped")
        assert saved.inner_text().split("\n")[0].startswith(partial[:25]), (partial, saved.inner_text())
        step("Stop kept the partial answer; after a reload the history shows it as stopped")

        # 3. The limit: the free plan allows 5 messages a minute.
        for index in range(6):
            page.fill("[data-testid=composer]", f"FAQ entry about delivery, version {index}")
            page.click("[data-testid=send]")
            page.wait_for_selector("[data-testid=notice], [data-testid=send]", timeout=15_000)
            if page.get_by_test_id("notice").count():
                break
        expect(page.get_by_test_id("notice")).to_contain_text("Too many messages")
        assert "version" in page.input_value("[data-testid=composer]"), "the refused text was lost"
        page.screenshot(path=DOCS / "chat-limit.png")
        step("the burst limit refused a message, said why, and gave the text back")

        # 4. Admin is closed to a normal user.
        page.goto(f"{web}/admin")
        page.wait_for_url(f"{web}/app")
        assert page.request.get(f"{web}/api/admin/users").status == 403
        step("a normal user is sent away from /admin and the API answers 403")

        page.goto(f"{web}/app/account")
        expect(page.get_by_text("Messages today")).to_be_visible()
        page.screenshot(path=DOCS / "account.png")
        page.click("button:has-text('Sign out')")
        page.wait_for_url(f"{web}/login")
        assert page.request.get(f"{web}/api/auth/me").status == 401
        step("the account page shows usage; sign-out ends the session")

        # 5. Admin page.
        sign_in(page, web, *ADMIN)
        page.goto(f"{web}/admin")
        expect(page.get_by_test_id("admin-tiles")).to_be_visible()
        row = page.locator("[data-testid=admin-users] tbody tr", has_text=email)
        expect(row).to_contain_text("5 / 20")
        page.locator("svg[role=img] rect").nth(6).hover()
        page.screenshot(path=DOCS / "admin.png", full_page=True)
        row.locator("select").select_option("pro")
        expect(row).to_contain_text("5 / 500")
        row.locator("button:has-text('Deactivate')").click()
        expect(row.locator("button")).to_have_text("Reactivate")
        step("the admin page lists the new account with its usage; plan change and deactivation work")

        browser.close()
    print("E2E PASSED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default="http://localhost:3000")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    run(args.web.rstrip("/"), args.headed)
