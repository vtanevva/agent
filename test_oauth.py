#!/usr/bin/env python3
"""Test Google OAuth configuration"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv()

import os
from backend.services.gmail_auth import get_client_secrets_path, _build_client_config_from_env

print("=" * 60)
print("Google OAuth Configuration Test")
print("=" * 60)

# Check environment variables
print("\n1. Environment Variables:")
print(f"   GOOGLE_CLIENT_ID: {'✓ Set' if os.getenv('GOOGLE_CLIENT_ID') else '✗ Missing'}")
print(f"   GOOGLE_CLIENT_SECRET: {'✓ Set' if os.getenv('GOOGLE_CLIENT_SECRET') else '✗ Missing'}")
print(f"   OAUTH_REDIRECT_URI: {os.getenv('OAUTH_REDIRECT_URI', 'Not set')}")

# Check if we can build config from env
print("\n2. OAuth Client Config:")
config = _build_client_config_from_env()
if config:
    print("   ✓ Can build OAuth config from environment variables")
    if 'web' in config:
        print(f"   Client ID: {config['web'].get('client_id', 'N/A')[:20]}...")
        print(f"   Redirect URIs: {config['web'].get('redirect_uris', [])}")
else:
    print("   ✗ Cannot build OAuth config")

# Check credentials path
print("\n3. Credentials File:")
try:
    creds_path = get_client_secrets_path()
    print(f"   Path: {creds_path}")
    print(f"   Exists: {'✓ Yes' if creds_path.exists() else '✗ No (will be created from env vars)'}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("OAuth setup is", "READY ✓" if config else "NOT CONFIGURED ✗")
print("=" * 60)
