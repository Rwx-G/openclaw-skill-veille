#!/usr/bin/env python3
"""
setup.py - Wizard interactif d'initialisation et de gestion du skill veille.

Modes :
  python3 setup.py                  # wizard initial (creation config + dirs)
  python3 setup.py --manage-sources # gestion interactive des sources RSS
  python3 setup.py --non-interactive

Actions du wizard initial :
  1. Cree ~/.openclaw/config/veille/ et ~/.openclaw/data/veille/
  2. Copie config.example.json -> config.json si absent
  3. Propose hours_lookback et max_articles_per_source

Actions du menu sources :
  - Affiche toutes les sources disponibles (actives + desactivees)
  - Permet de basculer chaque source entre active et desactivee
  - Sauvegarde le config.json mis a jour
"""

import argparse
import json
import sys
from pathlib import Path

# ---- Paths ------------------------------------------------------------------

SKILL_DIR    = Path(__file__).resolve().parent.parent
_CONFIG_DIR  = Path.home() / ".openclaw" / "config" / "veille"
_DATA_DIR    = Path.home() / ".openclaw" / "data" / "veille"
CONFIG_FILE  = _CONFIG_DIR / "config.json"
EXAMPLE_FILE = SKILL_DIR / "config.example.json"


# ---- Helpers ----------------------------------------------------------------


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


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Could not read {path}: {e}", file=sys.stderr)
    return {}


def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _real_sources(sources: dict) -> dict:
    """Retourne les sources sans les cles _comment_*."""
    return {k: v for k, v in sources.items() if not k.startswith("_")}


# ---- Initial setup ----------------------------------------------------------


def run_setup(interactive: bool = True):
    print()
    print("=" * 52)
    print("  OpenClaw Skill Veille - Setup")
    print("=" * 52)

    # Step 1: Create directories
    print()
    print("[1/3] Creating directories...")
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  OK  {_CONFIG_DIR}")
    print(f"  OK  {_DATA_DIR}")

    # Load example config as base
    if not EXAMPLE_FILE.exists():
        print(f"\n[ERROR] config.example.json not found at {EXAMPLE_FILE}", file=sys.stderr)
        sys.exit(1)

    example_cfg = _load_json(EXAMPLE_FILE)

    # Step 2: Configuration options
    print()
    print("[2/3] Configuration...")
    default_hours = str(example_cfg.get("hours_lookback", 24))
    hours_str = _ask("  Lookback window (hours)", default_hours, interactive)
    try:
        hours = int(hours_str)
    except ValueError:
        hours = int(default_hours)
    example_cfg["hours_lookback"] = hours

    default_max = str(example_cfg.get("max_articles_per_source", 20))
    max_str = _ask("  Max articles per source", default_max, interactive)
    try:
        max_arts = int(max_str)
    except ValueError:
        max_arts = int(default_max)
    example_cfg["max_articles_per_source"] = max_arts

    # Step 3: Write config
    print()
    print("[3/3] Writing config file...")
    if CONFIG_FILE.exists():
        print(f"  [WARN] Config already exists: {CONFIG_FILE}")
        if _confirm("  Overwrite with defaults?", interactive):
            _save_json(CONFIG_FILE, example_cfg)
            print(f"  OK  {CONFIG_FILE} (overwritten)")
        else:
            print(f"  SKIP {CONFIG_FILE} (kept existing)")
    else:
        _save_json(CONFIG_FILE, example_cfg)
        print(f"  OK  {CONFIG_FILE} (created)")

    # Summary
    print()
    print("=" * 52)
    print("  Setup complete!")
    print()
    print(f"  Config : {CONFIG_FILE}")
    print(f"  Data   : {_DATA_DIR}/")
    print()
    print("  Next steps:")
    print("    python3 init.py                          # validate")
    print("    python3 setup.py --manage-sources        # toggle RSS feeds")
    print("    python3 veille.py fetch --hours 24")
    print("=" * 52)
    print()


# ---- Source management ------------------------------------------------------


def _build_catalog(example_cfg: dict, user_cfg: dict) -> list:
    """
    Construit le catalogue complet des sources avec leur statut.
    Retourne une liste de dicts :
      { "name": str, "url": str, "active": bool, "category": str }
    """
    catalog = []
    current_category = "General"

    example_sources  = example_cfg.get("sources", {})
    example_disabled = example_cfg.get("sources_disabled", {})
    user_sources     = user_cfg.get("sources", {})
    user_disabled    = user_cfg.get("sources_disabled", {})

    # Active in user config: source is in user sources (non-comment keys)
    user_active_names = set(_real_sources(user_sources).keys())

    # All known sources = example sources + example disabled + user custom
    all_known: dict = {}

    for name, val in example_sources.items():
        if name.startswith("_comment"):
            # Extract category label from comment value
            current_category = val.strip("- ").strip()
            continue
        all_known[name] = {"url": val, "category": current_category}

    current_category = "Autres"
    for name, val in example_disabled.items():
        if name.startswith("_"):
            continue
        if name not in all_known:
            all_known[name] = {"url": val, "category": "Autres"}

    # User custom sources not in example
    for name, val in _real_sources(user_sources).items():
        if name not in all_known:
            all_known[name] = {"url": val, "category": "Custom"}
    for name, val in _real_sources(user_disabled).items():
        if name not in all_known:
            all_known[name] = {"url": val, "category": "Custom"}

    # Build catalog list
    for name, info in all_known.items():
        catalog.append({
            "name":     name,
            "url":      info["url"],
            "active":   name in user_active_names,
            "category": info["category"],
        })

    return catalog


def _display_catalog(catalog: list):
    """Affiche le catalogue avec numero, statut et categorie."""
    current_cat = None
    for i, entry in enumerate(catalog):
        if entry["category"] != current_cat:
            current_cat = entry["category"]
            print(f"\n  --- {current_cat} ---")
        status = "[ON] " if entry["active"] else "[off]"
        print(f"  {i + 1:2d}. {status} {entry['name']}")


def _apply_catalog(catalog: list, example_cfg: dict, user_cfg: dict) -> dict:
    """
    Reconstruit sources et sources_disabled a partir du catalogue.
    Preserve les cles _comment_* de l'exemple dans sources.
    """
    active_names   = {e["name"] for e in catalog if e["active"]}
    inactive_names = {e["name"] for e in catalog if not e["active"]}

    all_urls = {e["name"]: e["url"] for e in catalog}

    # Rebuild sources: keep _comment_ keys in order from example, add active
    new_sources: dict = {}
    example_sources = example_cfg.get("sources", {})
    # Preserve comment keys and order from example, include active sources
    for name, val in example_sources.items():
        if name.startswith("_comment"):
            new_sources[name] = val
        elif name in active_names:
            new_sources[name] = all_urls[name]

    # Custom active sources not in example
    for name in active_names:
        if name not in new_sources:
            new_sources[name] = all_urls[name]

    # Rebuild sources_disabled
    new_disabled: dict = {}
    example_disabled = example_cfg.get("sources_disabled", {})
    for name, val in example_disabled.items():
        if name.startswith("_"):
            new_disabled[name] = val
            continue
        if name in inactive_names:
            new_disabled[name] = all_urls[name]

    # Custom inactive sources not in example disabled
    for name in inactive_names:
        if name not in new_disabled:
            new_disabled[name] = all_urls[name]

    result = dict(user_cfg)
    result["sources"] = new_sources
    result["sources_disabled"] = new_disabled
    return result


def run_manage_sources():
    """Menu interactif de gestion des sources RSS."""
    print()
    print("=" * 52)
    print("  Veille - Gestion des sources RSS")
    print("=" * 52)

    if not CONFIG_FILE.exists():
        print(f"\n[WARN] {CONFIG_FILE} not found. Run setup.py first.", file=sys.stderr)
        if not EXAMPLE_FILE.exists():
            print("[ERROR] config.example.json not found either.", file=sys.stderr)
            sys.exit(1)
        print("Using config.example.json as base.\n")

    example_cfg = _load_json(EXAMPLE_FILE)
    user_cfg    = _load_json(CONFIG_FILE) if CONFIG_FILE.exists() else dict(example_cfg)

    catalog = _build_catalog(example_cfg, user_cfg)

    print(f"\n  Config : {CONFIG_FILE}")
    print("  Statut : [ON] = active, [off] = desactivee")
    print("  Action : entrer un ou plusieurs numeros (ex: 3 5 7) pour basculer")
    print("           'q' pour sauvegarder et quitter")
    print("           'r' pour reafficher la liste")

    while True:
        print()
        _display_catalog(catalog)
        print()

        try:
            raw = input("  Numeros a basculer (ou q/r): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raw = "q"

        if raw.lower() == "q":
            break
        if raw.lower() == "r":
            continue
        if not raw:
            continue

        # Parse numbers
        changed = False
        for token in raw.replace(",", " ").split():
            try:
                idx = int(token) - 1
                if 0 <= idx < len(catalog):
                    catalog[idx]["active"] = not catalog[idx]["active"]
                    name = catalog[idx]["name"]
                    status = "ON" if catalog[idx]["active"] else "off"
                    print(f"  -> {name}: {status}")
                    changed = True
                else:
                    print(f"  [WARN] Numero {token} hors plage (1-{len(catalog)})")
            except ValueError:
                print(f"  [WARN] '{token}' n'est pas un nombre")

    # Save
    updated = _apply_catalog(catalog, example_cfg, user_cfg)
    _save_json(CONFIG_FILE, updated)

    active_count = sum(1 for e in catalog if e["active"])
    print()
    print(f"  Sauvegarde : {active_count} sources actives -> {CONFIG_FILE}")
    print()


# ---- Main -------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="OpenClaw veille - setup wizard")
    parser.add_argument("--manage-sources", action="store_true",
                        help="Gestion interactive des sources RSS (activer/desactiver)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Utilise les valeurs par defaut sans prompts")
    args = parser.parse_args()

    if args.manage_sources:
        run_manage_sources()
    else:
        run_setup(interactive=not args.non_interactive)


if __name__ == "__main__":
    main()
