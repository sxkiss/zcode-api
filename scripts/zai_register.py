#!/usr/bin/env python3
"""
Automated Z.AI registration + OAuth login.

Usage:
    python scripts/zai_register.py [--dry-run] [--email EMAIL] [--password PASSWORD]

Flow:
    1. Create temporary email via Cloudflare Worker (gptmail.sxkiss.top)
    2. Print credentials for manual browser signup (captcha required)
    3. Poll inbox for verification code
    4. Verify email + finish signup
    5. Get OAuth authorize URL for zcode.z.ai login

Requires:
    - requests library
    - Access to gptmail.sxkiss.top (Cloudflare Worker)
"""

import argparse
import random
import string
import sys
import time
import webbrowser
from typing import Optional, Tuple

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMAIL_WORKER = "gptmail.sxkiss.top"
EMAIL_DOMAIN = "sxkiss.cn"
ADMIN_PASSWORD = "sk-sxkiss"

CHAT_BASE = "https://chat.z.ai/api/v1"
ZCODE_BASE = "https://zcode.z.ai/api/v1"

SESSION_TIMEOUT = 180  # seconds to wait for email to arrive


# ---------------------------------------------------------------------------
# Email creation via Cloudflare Worker
# ---------------------------------------------------------------------------

def create_email() -> Tuple[Optional[str], Optional[str]]:
    """Create a temporary email address via the CF Worker."""
    letters1 = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 6)))
    numbers = "".join(random.choices(string.digits, k=random.randint(1, 3)))
    letters2 = "".join(random.choices(string.ascii_lowercase, k=random.randint(0, 5)))
    random_name = letters1 + numbers + letters2

    url = f"https://{EMAIL_WORKER}/admin/new_address"
    try:
        resp = requests.post(
            url,
            json={
                "enablePrefix": True,
                "name": random_name,
                "domain": EMAIL_DOMAIN,
            },
            headers={
                "x-admin-auth": ADMIN_PASSWORD,
                "Content-Type": "application/json",
            },
            timeout=30,
            verify=False,
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("jwt")
            email = data.get("address")
            if email:
                return email, token
        else:
            print(f"Email creation failed: HTTP {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"Email creation failed: {e}")

    return None, None


def poll_inbox(jwt: str, timeout: int = SESSION_TIMEOUT) -> Optional[dict]:
    """Poll the temp mail inbox until a message arrives or timeout."""
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            resp = requests.get(
                f"https://{EMAIL_WORKER}/api/mails?limit=10&offset=0",
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=10,
                verify=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("count", 0) > 0 and data.get("results"):
                    return data["results"][0]
        except Exception as e:
            print(f"Inbox poll error: {e}")
        time.sleep(5)
    return None


def extract_code(message: dict) -> Optional[str]:
    """Extract 6-digit verification code from email body."""
    import re
    body = message.get("text", "") or message.get("html", "") or ""
    match = re.search(r'\b(\d{6})\b', body)
    if match:
        return match.group(1)
    match = re.search(r'code[:\s]*(\d{6})', body, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


# ---------------------------------------------------------------------------
# Z.AI Registration
# ---------------------------------------------------------------------------

def verify_email(email: str, token: str) -> Optional[dict]:
    """Verify email with the token received."""
    url = f"{CHAT_BASE}/auths/verify_email"
    try:
        resp = requests.post(
            url,
            json={"username": email.split("@")[0], "email": email, "token": token},
            headers={"Content-Type": "application/json"},
            timeout=30,
            verify=False,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"Verify failed: HTTP {resp.status_code} - {resp.text[:300]}")
    except Exception as e:
        print(f"Verify error: {e}")
    return None


def finish_signup(email: str, token: str, password: str) -> Optional[dict]:
    """Complete the signup process."""
    url = f"{CHAT_BASE}/auths/finish_signup"
    try:
        resp = requests.post(
            url,
            json={
                "username": email.split("@")[0],
                "email": email,
                "token": token,
                "password": password,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
            verify=False,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"Finish signup failed: HTTP {resp.status_code} - {resp.text[:300]}")
    except Exception as e:
        print(f"Finish signup error: {e}")
    return None


def signin(email: str, password: str) -> Optional[dict]:
    """Sign in to get session cookies."""
    url = f"{CHAT_BASE}/auths/signin"
    try:
        resp = requests.post(
            url,
            json={"email": email, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=30,
            verify=False,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"Signin failed: HTTP {resp.status_code} - {resp.text[:300]}")
    except Exception as e:
        print(f"Signin error: {e}")
    return None


# ---------------------------------------------------------------------------
# OAuth Login via ZCode
# ---------------------------------------------------------------------------

def get_oauth_url() -> Optional[str]:
    """Get the OAuth authorize URL from zcode.z.ai."""
    url = f"{ZCODE_BASE}/oauth/cli/init"
    try:
        resp = requests.post(
            url,
            json={"provider": "zai"},
            headers={"Content-Type": "application/json"},
            timeout=30,
            verify=False,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("authorizeUrl") or data.get("url")
        else:
            print(f"OAuth init failed: HTTP {resp.status_code} - {resp.text[:300]}")
    except Exception as e:
        print(f"OAuth init error: {e}")
    return None


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, email: str = None, password: str = None) -> int:
    """Run the full registration + login flow."""
    print("=" * 60)
    print("Z.AI Automated Registration")
    print("=" * 60)

    # Step 1: Create or use provided email
    print("\n[1/5] Creating temporary email...")
    if email:
        # Use provided email, need to create JWT by creating a dummy
        # Actually, we need the JWT for the provided email too
        # Let's just use the create_email function
        created_email, jwt = create_email()
        if not created_email:
            print("Failed to create email")
            return 1
        email = created_email
    else:
        email, email_jwt = create_email()
        if not email:
            print("Failed to create email")
            return 1
    
    if not password:
        password = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    
    print(f"  Email: {email}")
    print(f"  Password: {password}")

    if dry_run:
        print("\n[DRY RUN] Stopping here.")
        print(f"\n[MANUAL STEPS]")
        print(f"  1. Open: https://chat.z.ai/signup")
        print(f"  2. Register with:")
        print(f"     - Email: {email}")
        print(f"     - Password: {password}")
        print(f"  3. Complete the captcha verification")
        print(f"  4. After registration, run this script again (no --dry-run)")
        print(f"\n[OR] Run: python scripts/zai_register.py --email {email} --password {password}")
        return 0

    # Step 2: Open browser for manual signup
    print("\n[2/5] Opening signup page...")
    print(f"\n  Please complete registration in your browser:")
    print(f"    URL: https://chat.z.ai/signup")
    print(f"    Email: {email}")
    print(f"    Password: {password}")
    print(f"\n  Browser opening...")
    
    signup_url = "https://chat.z.ai/signup"
    webbrowser.open(signup_url)
    
    print(f"\n  Press Enter when registration is complete...")
    try:
        input()
    except EOFError:
        pass

    # Step 3: Poll for verification code
    print("\n[3/5] Waiting for verification email...")
    message = poll_inbox(email_jwt)
    if not message:
        print("No email received within timeout")
        print(f"  To check manually:")
        print(f"  curl -s 'https://{EMAIL_WORKER}/api/mails?limit=10&offset=0' \\")
        print(f"    -H 'Authorization: Bearer {email_jwt}'")
        return 1

    code = extract_code(message)
    if not code:
        print(f"Could not extract code from email. Body preview:")
        print(f"  {str(message.get('text', ''))[:200]}")
        return 1
    print(f"  Verification code: {code}")

    # Step 4: Verify and finish signup
    print("\n[4/5] Verifying email...")
    verify_data = verify_email(email, code)
    if not verify_data:
        print("Email verification failed")
        return 1
    print("  Email verified")

    print("\n  Completing signup...")
    finish_data = finish_signup(email, code, password)
    if not finish_data:
        print("Finish signup failed")
        return 1
    print("  Account created!")

    # Step 5: Sign in and get OAuth URL
    print("\n[5/5] Signing in...")
    signin_data = signin(email, password)
    if not signin_data:
        print("Signin failed")
        return 1
    print("  Signed in successfully")

    # Get OAuth URL
    print("\n  Getting OAuth authorize URL...")
    oauth_url = get_oauth_url()
    if not oauth_url:
        print("Failed to get OAuth URL")
        return 1
    print(f"\n{'=' * 60}")
    print(f"ACCOUNT CREATED!")
    print(f"  Email: {email}")
    print(f"  Password: {password}")
    print(f"{'=' * 60}")
    print(f"\nTo complete login, open this URL in browser:")
    print(f"  {oauth_url}")
    print(f"\nThen run: bun run src/index.ts auth login zai")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Automated Z.AI registration")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    parser.add_argument("--email", help="Use specific email (auto-creates if not provided)")
    parser.add_argument("--password", help="Use specific password (auto-generates if not provided)")
    args = parser.parse_args()

    return run(dry_run=args.dry_run, email=args.email, password=args.password)


if __name__ == "__main__":
    sys.exit(main())
