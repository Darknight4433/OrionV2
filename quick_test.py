#!/usr/bin/env python3
"""
Quick validation script to check for import errors
"""

print("Testing basic imports...")

try:
    import sys
    print("✓ sys")
except Exception as e:
    print(f"✗ sys: {e}")

try:
    import os
    print("✓ os")
except Exception as e:
    print(f"✗ os: {e}")

try:
    import json
    print("✓ json")
except Exception as e:
    print(f"✗ json: {e}")

try:
    import requests
    print("✓ requests")
except Exception as e:
    print(f"✗ requests: {e}")

try:
    import telegram
    print("✓ telegram")
except Exception as e:
    print(f"✗ telegram: {e}")

try:
    from orion.core import router
    print("✓ orion.core.router")
except Exception as e:
    print(f"✗ orion.core.router: {e}")

try:
    from orion.core import dev_monitor
    print("✓ orion.core.dev_monitor")
except Exception as e:
    print(f"✗ orion.core.dev_monitor: {e}")

try:
    from orion.integrations import telegram_bot
    print("✓ orion.integrations.telegram_bot")
except Exception as e:
    print(f"✗ orion.integrations.telegram_bot: {e}")

print("Import test complete.")