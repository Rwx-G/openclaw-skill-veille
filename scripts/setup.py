#!/usr/bin/env python3
"""
setup.py - Wizard interactif d'initialisation du skill veille.

Actions :
  1. Cree ~/.openclaw/config/veille/ et ~/.openclaw/data/veille/
  2. Propose hours_lookback (defaut 24)
  3. Copie config.example.json -> ~/.openclaw/config/veille/config.json
     (demande confirmation si deja present)
  4. Affiche les chemins ecrits

Usage :
  python3 setup.py
  python3 setup.py --non-interactive   (utilise les defauts sans prompt)
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# ---- Paths ------------------------------------------------------------------

SKILL_DIR   = Path(__file__).resolve().parent.parent
_CONFIG_DIR = Path.home() / ".openclaw" / "config" / "veille"
_DATA_DIR   = Path.home() / ".openclaw" / "data" / "veille"
CONFIG_FILE = _CONFIG_DIR / "config.json"
EXAMPLE_FILE = SKILL_DIR / "config.example.json"


def _ask(prompt: str, default: str, interactive: bool) -> str:
    if not interactive:
        return default
    try:
        answer = input(f"{prompt} [{default}]: ").strip()
        return answer if answer else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def _confirm(prompt: str, interactive: bool) -> bool:
    if not interactive:
        return False
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
        return answer in ("y", "yes", "o", "oui")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def run_setup(interactive: bool = True):
    print("=== OpenClaw Skill Veille - Setup ===")
    print()

    # Step 1: Create directories
    print("[1/3] Creating directories...")
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  OK  {_CONFIG_DIR}")
    print(f"  OK  {_DATA_DIR}")
    print()

    # Step 2: Check example config
    if not EXAMPLE_FILE.exists():
        print(f"[ERROR] config.example.json not found at {EXAMPLE_FILE}", file=sys.stderr)
        print("        Make sure you are running setup.py from the skill directory.", file=sys.stderr)
        sys.exit(1)

    # Load example config
    example_cfg = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))

    # Ask for hours_lookback
    print("[2/3] Configuration...")
    default_hours = str(example_cfg.get("hours_lookback", 24))
    hours_str = _ask("  Default lookback window (hours)", default_hours, interactive)
    try:
        hours = int(hours_str)
    except ValueError:
        hours = int(default_hours)
    example_cfg["hours_lookback"] = hours
    print()

    # Step 3: Write config
    print("[3/3] Writing config file...")
    if CONFIG_FILE.exists():
        print(f"  [WARN] Config already exists: {CONFIG_FILE}")
        if _confirm("  Overwrite?", interactive):
            CONFIG_FILE.write_text(
                json.dumps(example_cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  OK  {CONFIG_FILE} (overwritten)")
        else:
            print(f"  SKIP {CONFIG_FILE} (kept existing)")
    else:
        CONFIG_FILE.write_text(
            json.dumps(example_cfg, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  OK  {CONFIG_FILE} (created)")
    print()

    # Summary
    print("=== Setup complete ===")
    print()
    print("Files written:")
    print(f"  Config : {CONFIG_FILE}")
    print(f"  Data   : {_DATA_DIR}/")
    print()
    print("Next steps:")
    print("  python3 init.py      # validate setup")
    print("  python3 veille.py fetch --hours 24 --filter-seen --filter-topic")
    print()


def main():
    parser = argparse.ArgumentParser(description="OpenClaw veille - setup wizard")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Use defaults without prompting")
    args = parser.parse_args()
    run_setup(interactive=not args.non_interactive)


if __name__ == "__main__":
    main()
