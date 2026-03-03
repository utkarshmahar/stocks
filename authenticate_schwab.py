#!/usr/bin/env python3
"""
Schwab API Authentication Script
================================
Run this every 7 days to refresh your Schwab token.

Usage:
    python3 authenticate_schwab.py
"""

import sys
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load .env from this directory
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from schwab import auth

API_KEY = os.environ.get('SCHWAB_API_KEY', '')
APP_SECRET = os.environ.get('SCHWAB_APP_SECRET', '')
CALLBACK_URL = os.environ.get('SCHWAB_CALLBACK_URL', 'https://127.0.0.1')
TOKEN_PATH = os.path.join(os.path.dirname(__file__), 'schwab_token.json')


def check_existing_token():
    """Check if a valid token already exists"""
    if not os.path.exists(TOKEN_PATH):
        return False, "Token file does not exist"

    try:
        with open(TOKEN_PATH, 'r') as f:
            token_data = json.load(f)

        if 'creation_timestamp' in token_data:
            created = datetime.fromtimestamp(token_data['creation_timestamp'])
            expires = created + timedelta(days=7)
            days_left = (expires - datetime.now()).days

            if days_left > 0:
                return True, f"Token is valid. Expires in {days_left} days ({expires.strftime('%Y-%m-%d')})"
            else:
                return False, "Refresh token has expired (7+ days old)"

        return None, "Token exists but cannot verify expiration"

    except Exception as e:
        return False, f"Error reading token: {e}"


def authenticate():
    """Perform manual authentication flow"""
    print("=" * 70)
    print("SCHWAB API AUTHENTICATION")
    print("=" * 70)
    print()
    print("This will open your web browser for Schwab login.")
    print("After logging in, you'll be redirected to a URL that looks like:")
    print("  https://127.0.0.1/?code=XXXX&session=YYYY")
    print()
    print("IMPORTANT: Copy the ENTIRE URL from your browser's address bar!")
    print()
    print("=" * 70)
    print()

    try:
        input("Press ENTER to open browser and start authentication...")
        print()

        c = auth.client_from_manual_flow(
            api_key=API_KEY,
            app_secret=APP_SECRET,
            callback_url=CALLBACK_URL,
            token_path=TOKEN_PATH
        )

        # Add creation timestamp
        try:
            with open(TOKEN_PATH, 'r') as f:
                token_data = json.load(f)
            token_data['creation_timestamp'] = datetime.now().timestamp()
            with open(TOKEN_PATH, 'w') as f:
                json.dump(token_data, f, indent=2)
        except:
            pass

        print()
        print("=" * 70)
        print("AUTHENTICATION SUCCESSFUL!")
        print("=" * 70)
        print(f"Token saved to: {TOKEN_PATH}")
        print(f"Token valid for: 7 days")
        print(f"Next manual auth needed: {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')}")
        print()
        print("Restart ingestion service to pick up new token:")
        print("  sudo docker compose restart ingestion-service")
        print("=" * 70)
        return True

    except KeyboardInterrupt:
        print("\n\nAuthentication cancelled by user.")
        return False
    except Exception as e:
        print()
        print("=" * 70)
        print("AUTHENTICATION FAILED")
        print("=" * 70)
        print(f"Error: {e}")
        print()
        print("Common issues:")
        print("  1. Make sure you copied the COMPLETE redirect URL")
        print("  2. URL should start with https://127.0.0.1/?code=")
        print("  3. Check SCHWAB_API_KEY and SCHWAB_APP_SECRET in .env")
        print("=" * 70)
        return False


def main():
    print()
    print("Checking existing token...")
    print()

    valid, message = check_existing_token()

    if valid is True:
        print(f"{message}")
        print()
        response = input("Token is still valid. Re-authenticate anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Keeping existing token. Exiting.")
            return
    elif valid is None:
        print(f"{message}")
        print()
        response = input("Re-authenticate to be safe? (Y/n): ").strip().lower()
        if response == 'n':
            print("Keeping existing token. Exiting.")
            return
    else:
        print(f"{message}")
        print("Manual authentication required.")

    print()
    authenticate()


if __name__ == '__main__':
    main()
