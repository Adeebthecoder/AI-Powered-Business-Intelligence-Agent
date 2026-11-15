"""
make_env.py
-----------
Creates the ".env" settings file from ".env.example".

Every value written as GENERATE_ME in the example file is replaced with a
strong random value (database passwords and the login token secret). This way
no password is ever written in the source code.

How to run (from the backend folder):
    python scripts/make_env.py

It is safe to run again: if ".env" already exists it is left untouched.
"""

import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_FILE = PROJECT_ROOT / ".env.example"
ENV_FILE = PROJECT_ROOT / ".env"


def main():
    if ENV_FILE.exists():
        print(f".env already exists at {ENV_FILE}")
        print("Nothing was changed. Delete that file first if you want a fresh one.")
        return

    if not EXAMPLE_FILE.exists():
        sys.exit(f"Cannot find {EXAMPLE_FILE}. Run this from inside the project folder.")

    new_lines = []
    for line in EXAMPLE_FILE.read_text(encoding="utf-8").splitlines():
        # Only touch real settings lines, not comments.
        if not line.startswith("#") and line.endswith("=GENERATE_ME"):
            key = line.split("=", 1)[0]
            # token_hex gives letters and digits only, so it is safe inside a database URL.
            line = f"{key}={secrets.token_hex(24)}"
        new_lines.append(line)

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Created {ENV_FILE}")
    print("Random passwords and a login secret were generated for you.")
    print("The app starts in mock mode (LLM_MODE=mock). To use the real AI model,")
    print("open .env, paste your OpenRouter key and set LLM_MODE=live.")


if __name__ == "__main__":
    main()
