"""
set_secrets.py - One-time setup helper for the Claude SMS bot.

You paste your Anthropic key and Twilio Auth Token. The script:
  - Validates the format
  - Pipes them to `flyctl secrets import` via stdin (so they never
    appear in PowerShell history or process arguments)
  - Wipes the local Python variables holding them
  - Clears the terminal screen so they don't linger in scrollback

The keys WILL briefly show on your screen as you paste. That's
local-only - nothing leaves your PC except the encrypted upload to
Fly.io. The screen-clear at the end removes the visible trace.

Run from this folder:
    py -3 set_secrets.py

Re-run anytime you rotate keys.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent
FLY_TOML = APP_DIR / "fly.toml"


def die(msg):
    print(f"\nERROR: {msg}\n")
    sys.exit(1)


def main():
    if not FLY_TOML.exists():
        die(f"fly.toml not found in {APP_DIR}.\nRun this from the claude_sms_bot folder.")

    # Confirm flyctl exists and we're authed
    check = subprocess.run(
        ["flyctl", "auth", "whoami"],
        capture_output=True, text=True, cwd=APP_DIR,
    )
    if check.returncode != 0:
        die("flyctl not installed or not logged in. Run `flyctl auth login` first.")
    print(f"Logged in as: {check.stdout.strip()}")
    print()

    print("=" * 60)
    print("  CLAUDE SMS BOT - secret setup")
    print("=" * 60)
    print()
    print("Paste your two keys when asked. They WILL show on screen as")
    print("you paste - that's local-only, nothing is sent to chat or any")
    print("third party. The screen will be cleared after both are entered.")
    print()
    print("To paste in PowerShell: right-click in the window. (Ctrl+V works")
    print("only in Windows Terminal, not the classic blue PowerShell.)")
    print()
    print("Where to find them:")
    print("  Anthropic key:  https://console.anthropic.com/settings/keys")
    print("  Twilio token:   https://console.twilio.com (front page)")
    print()

    # --- Anthropic key ---
    while True:
        key = input("Anthropic API key (sk-ant-...): ").strip()
        if not key:
            print("  (empty - try again)")
            continue
        if not key.startswith("sk-ant-"):
            print("  That doesn't start with 'sk-ant-'. Try again.")
            continue
        if len(key) < 50:
            print("  That's too short to be a real key. Try again.")
            continue
        break

    # --- Twilio token ---
    while True:
        token = input("Twilio Auth Token (32 hex chars): ").strip()
        if not token:
            print("  (empty - try again)")
            continue
        if not re.fullmatch(r"[a-fA-F0-9]{32}", token):
            print(f"  Should be 32 hex characters, got {len(token)}. Try again.")
            continue
        token = token.lower()
        break

    # --- Clear screen so the secrets don't linger in scrollback ---
    os.system("cls" if os.name == "nt" else "clear")
    print("Both keys captured. Setting Fly.io secrets...")
    secrets_blob = f"ANTHROPIC_API_KEY={key}\nTWILIO_AUTH_TOKEN={token}\n"

    result = subprocess.run(
        ["flyctl", "secrets", "import"],
        input=secrets_blob,
        text=True,
        cwd=APP_DIR,
    )

    # Wipe local copies of the secrets ASAP
    key = token = secrets_blob = None

    if result.returncode != 0:
        die("flyctl secrets import failed. See output above.")

    print()
    print("Secrets stored encrypted on Fly.io. Local copies discarded.")
    print()

    # --- Deploy ---
    answer = input("Deploy now? [Y/n]: ").strip().lower()
    if answer in ("", "y", "yes"):
        print()
        print("Deploying... (first build takes 2-3 minutes)")
        deploy = subprocess.run(["flyctl", "deploy"], cwd=APP_DIR)
        if deploy.returncode != 0:
            die("Deploy failed. See output above.")

        print()
        print("=" * 60)
        print("  DEPLOYED")
        print("=" * 60)
        # Show the URL
        subprocess.run(["flyctl", "status"], cwd=APP_DIR)
        print()
        print("Final step: paste https://YOUR-APP.fly.dev/sms into Twilio")
        print("(Phone Numbers -> your number -> Messaging Configuration)")
    else:
        print("Skipped deploy. Run `flyctl deploy` when ready.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
