#!/usr/bin/env python3
"""
Z.AI Registration via CDP — uses existing Chrome pages.
Creates email, opens/chk signup page, waits for captcha completion,
then polls inbox, verifies, finishes signup, gets OAuth URL.
"""
import asyncio
import json
import random
import string
import sys
import time
from typing import Optional, Tuple

try:
    from playwright.async_api import async_playwright
    import requests
except ImportError:
    print("Error: playwright and requests required", flush=True)
    sys.exit(1)

EMAIL_WORKER = "gptmail.sxkiss.top"
EMAIL_DOMAIN = "sxkiss.cn"
ADMIN_PASSWORD = "sk-sxkiss"
CHAT_BASE = "https://chat.z.ai/api/v1"
ZCODE_BASE = "https://zcode.z.ai/api/v1"
CDP_URL = "http://127.0.0.1:9222"


def create_email() -> Tuple[Optional[str], Optional[str]]:
    letters1 = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 6)))
    numbers = "".join(random.choices(string.digits, k=random.randint(1, 3)))
    letters2 = "".join(random.choices(string.ascii_lowercase, k=random.randint(0, 5)))
    resp = requests.post(
        f"https://{EMAIL_WORKER}/admin/new_address",
        json={"enablePrefix": True, "name": letters1 + numbers + letters2, "domain": EMAIL_DOMAIN},
        headers={"x-admin-auth": ADMIN_PASSWORD, "Content-Type": "application/json"},
        timeout=30, verify=False
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("address"), data.get("jwt")
    return None, None


def poll_inbox(jwt: str, timeout: int = 180) -> Optional[dict]:
    end = time.time() + timeout
    while time.time() < end:
        try:
            resp = requests.get(
                f"https://{EMAIL_WORKER}/api/mails?limit=10&offset=0",
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=10, verify=False
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("count", 0) > 0 and data.get("results"):
                    return data["results"][0]
        except Exception:
            pass
        time.sleep(5)
    return None


def extract_code(msg: dict) -> Optional[str]:
    import re
    body = msg.get("text", "") or msg.get("html", "") or ""
    m = re.search(r'\b(\d{6})\b', body)
    if m: return m.group(1)
    m = re.search(r'code[:\s]*(\d{6})', body, re.IGNORECASE)
    if m: return m.group(1)
    return None


def verify_email(email: str, token: str) -> bool:
    resp = requests.post(f"{CHAT_BASE}/auths/verify_email",
        json={"username": email.split("@")[0], "email": email, "token": token},
        headers={"Content-Type": "application/json"}, timeout=30, verify=False)
    return resp.status_code == 200


def finish_signup(email: str, token: str, password: str) -> bool:
    resp = requests.post(f"{CHAT_BASE}/auths/finish_signup",
        json={"username": email.split("@")[0], "email": email, "token": token, "password": password},
        headers={"Content-Type": "application/json"}, timeout=30, verify=False)
    return resp.status_code == 200


def signin(email: str, password: str) -> bool:
    resp = requests.post(f"{CHAT_BASE}/auths/signin",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"}, timeout=30, verify=False)
    return resp.status_code == 200


def get_oauth_url() -> Optional[str]:
    resp = requests.post(f"{ZCODE_BASE}/oauth/cli/init",
        json={"provider": "zai"},
        headers={"Content-Type": "application/json"}, timeout=30, verify=False)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("authorizeUrl") or data.get("url")
    return None


async def browser_wait_for_signup(email: str, password: str) -> bool:
    """Connect to existing Chrome via CDP, find Z.AI signup page, wait for captcha completion."""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"CDP connection failed: {e}", flush=True)
            return False

        # 找已有的signup页面
        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "chat.z.ai/signup" in pg.url:
                    page = pg
                    break
            if page:
                break

        if not page:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            try:
                await page.goto('https://www.baidu.com', wait_until='domcontentloaded', timeout=10000)
                print("Baidu OK", flush=True)
            except Exception as e:
                print(f"Baidu failed: {e}", flush=True)
            try:
                await page.goto("https://chat.z.ai/signup", wait_until='domcontentloaded', timeout=45000)
                print("Z.AI signup loaded", flush=True)
            except Exception as e:
                print(f"Z.AI failed: {e}", flush=True)
                await browser.close()
                return False

        print(f"Current page: {page.url}", flush=True)
        title = await page.title()
        print(f"Title: {title}", flush=True)

        # 截图
        try:
            await page.screenshot(path='/tmp/zai_current.png', full_page=True)
            print("Screenshot saved: /tmp/zai_current.png", flush=True)
        except Exception as e:
            print(f"Screenshot failed: {e}", flush=True)

        # 等待页面跳转到 /chat（表示注册完成）
        print("Waiting for captcha completion and redirect to /chat... (max 5 min)", flush=True)
        try:
            await page.wait_for_url("**/chat**", timeout=300000)
            print("Registration complete! Redirected to /chat", flush=True)
        except Exception as e:
            print(f"Timeout: {e}", flush=True)
            try:
                current_url = await page.evaluate("window.location.href")
                print(f"Current URL: {current_url}", flush=True)
            except:
                pass

        await browser.close()
        return True


async def main():
    print("=" * 60, flush=True)
    print("Z.AI Registration (CDP mode)", flush=True)
    print("=" * 60, flush=True)

    # Step 1: Create email
    print("\n[1/4] Creating email...", flush=True)
    email, jwt = create_email()
    if not email:
        print("Failed to create email", flush=True)
        return 1
    password = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    print(f"  Email: {email}", flush=True)
    print(f"  Password: {password}", flush=True)

    # Step 2: Browser captcha
    print("\n[2/4] Checking browser for Z.AI signup page...", flush=True)
    success = await browser_wait_for_signup(email, password)
    if not success:
        print("Browser check failed", flush=True)
        return 1

    # Step 3: Poll for code and verify
    print("\n[3/4] Waiting for verification email...", flush=True)
    msg = poll_inbox(jwt, timeout=180)
    if not msg:
        print("No email received", flush=True)
        return 1

    code = extract_code(msg)
    if not code:
        print("Could not extract code", flush=True)
        return 1
    print(f"  Code: {code}", flush=True)

    print("\n  Verifying email...", flush=True)
    if not verify_email(email, code):
        print("Verify failed", flush=True)
        return 1
    print("  Verified!", flush=True)

    print("\n  Finishing signup...", flush=True)
    if not finish_signup(email, code, password):
        print("Finish signup failed", flush=True)
        return 1
    print("  Signup complete!", flush=True)

    # Step 4: Sign in and get OAuth URL
    print("\n[4/4] Signing in...", flush=True)
    if not signin(email, password):
        print("Signin failed", flush=True)
        return 1

    oauth_url = get_oauth_url()
    if not oauth_url:
        print("Failed to get OAuth URL", flush=True)
        return 1

    print(f"\n{'=' * 60}", flush=True)
    print(f"SUCCESS!", flush=True)
    print(f"  Email: {email}", flush=True)
    print(f"  Password: {password}", flush=True)
    print(f"{'=' * 60}", flush=True)
    print(f"\nOpen this URL to authorize:", flush=True)
    print(f"  {oauth_url}", flush=True)
    print(f"\nThen: bun run src/index.ts auth login zai", flush=True)
    return 0


if __name__ == "__main__":
    asyncio.run(main())
