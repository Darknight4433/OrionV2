#!/usr/bin/env python3
"""
ORION Client Runner
===================
Starts the headless terminal-based ORION client.

This replaces the GUI-based client with a simpler, more reliable
terminal interface optimized for headless deployment.

Usage:
    python run_client.py
"""

import sys
import os
from headless_client import main

if __name__ == "__main__":
    print("\n" + "="*70)
    print("ORION HEADLESS CLIENT")
    print("="*70)
    print("\nStarting ORION client...")
    print("Make sure the backend is running: python backend/app/main.py\n")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ Client shut down by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Client error: {e}")
        sys.exit(1)
