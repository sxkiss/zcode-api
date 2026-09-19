#!/usr/bin/env python3
"""
Create Cloudflare Worker domain email addresses.

Usage:
    python create_cf_email.py <worker_domain> <email_domain> <admin_password>

This script mirrors the Cloudflare Worker email creation logic from the codexcpa
project (email_service.py _CloudflareWorkerBackend.create_address).
"""

import random
import string
import sys
import json
from typing import Optional, Tuple

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)


def create_address(worker_domain: str, email_domain: str, admin_password: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Create a temporary email address via Cloudflare Worker.
    
    Returns:
        Tuple of (email, token) or (None, None) on failure.
    """
    # Generate random email name: letters1 + numbers + letters2
    letters1 = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 6)))
    numbers = "".join(random.choices(string.digits, k=random.randint(1, 3)))
    letters2 = "".join(random.choices(string.ascii_lowercase, k=random.randint(0, 5)))
    random_name = letters1 + numbers + letters2

    url = f"https://{worker_domain}/admin/new_address"

    try:
        import requests as http_requests
        session = http_requests.Session()
        
        resp = session.post(
            url,
            json={
                "enablePrefix": True,
                "name": random_name,
                "domain": email_domain,
            },
            headers={
                "x-admin-auth": admin_password,
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


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: python create_cf_email.py <worker_domain> <email_domain> <admin_password>")
        print("  worker_domain: Cloudflare Worker domain (e.g., your-worker.com)")
        print("  email_domain: Email domain to use (e.g., example.com)")
        print("  admin_password: Admin password for the worker")
        return 1

    worker_domain = sys.argv[1]
    email_domain = sys.argv[2]
    admin_password = sys.argv[3]

    email, token = create_address(worker_domain, email_domain, admin_password)

    if email and token:
        print(f"SUCCESS: Email created")
        print(f"  Email: {email}")
        print(f"  Token: {token}")
        return 0
    else:
        print("FAILED: Could not create email address")
        return 1


if __name__ == "__main__":
    sys.exit(main())
