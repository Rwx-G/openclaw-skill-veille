#!/usr/bin/env python3
"""
dispatch.py - Output dispatcher for the OpenClaw veille skill.

Reads a digest JSON from stdin and dispatches to configured outputs.

Supported output types:
  telegram_bot  - Direct Telegram Bot API (token auto-read from OpenClaw config)
  mail-client   - Delegates to mail-client skill CLI (fallback: SMTP config)
  nextcloud     - Delegates to nextcloud skill CLI
  file          - Writes digest to a local file path

Content types per output:
  recap         - Short text summary (Telegram notifications)
  full_digest   - Full HTML (email) or Markdown (Nextcloud, file)

Input formats accepted (auto-detected):
  - Raw fetch:       {"hours": N, "count": N, "articles": [...], ...}
  - Processed LLM:   {"categories": [...], "ghost_picks": [...]}

Usage:
  python3 veille.py fetch --hours 24 --filter-seen | python3 veille.py send
  python3 veille.py fetch ... | python3 dispatch.py [--profile NAME]
"""

import html
import json
import pathlib
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CONFIG_DIR = pathlib.Path.home() / ".openclaw" / "config" / "veille"
_SKILLS_DIR = pathlib.Path.home() / ".openclaw" / "workspace" / "skills"
_OC_CONFIG  = pathlib.Path.home() / ".openclaw" / "openclaw.json"
CONFIG_PATH = _CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def _is_processed(data: dict) -> bool:
    """True if data is an LLM-processed digest with categories."""
    return "categories" in data


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_recap(data: dict) -> str:
    """Short plain-text recap (Telegram or similar)."""
    now = datetime.now(timezone.utc).strftime("%d/%m %H:%M")
    if _is_processed(data):
        categories = data.get("categories", [])
        count = sum(len(c.get("articles", [])) for c in categories)
        ghost_picks = data.get("ghost_picks", [])
        lines = [f"*Veille tech - {now}*", f"{count} articles"]
        for cat in categories:
            n = len(cat.get("articles", []))
            if n:
                lines.append(f"- {cat['name']}: {n}")
        if ghost_picks:
            lines.append(f"\n✍️ {len(ghost_picks)} candidat(s) Ghost")
    else:
        count = data.get("count", 0)
        skipped = data.get("skipped_url", 0) + data.get("skipped_topic", 0)
        hours = data.get("hours", 24)
        lines = [f"*Veille tech - {now}*", f"{count} articles ({hours}h)"]
        if skipped:
            lines.append(f"{skipped} filtré(s)")
    return "\n".join(lines)


def format_digest_markdown(data: dict) -> str:
    """Full Markdown digest for Nextcloud or file."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Veille technique - {now}", ""]

    if _is_processed(data):
        for cat in data.get("categories", []):
            lines += [f"## {cat['name']}", ""]
            for a in cat.get("articles", []):
                reason = a.get("reason", "")
                lines.append(f"- **[{a['title']}]({a['url']})**  ")
                lines.append(f"  *{a['source']} - {a.get('published', '')}*  ")
                if reason:
                    lines.append(f"  {reason}")
                lines.append("")
        picks = data.get("ghost_picks", [])
        if picks:
            lines += ["## ✍️ Candidats Ghost", ""]
            for p in picks:
                lines.append(f"- **[{p['title']}]({p['url']})**  ")
                lines.append(f"  *{p['source']}* - {p.get('reason', '')}")
                lines.append("")
    else:
        articles = data.get("articles", [])
        skipped = data.get("skipped_url", 0) + data.get("skipped_topic", 0)
        lines += [f"*{len(articles)} articles | {skipped} filtres*", ""]
        by_src: dict = {}
        for a in articles:
            by_src.setdefault(a.get("source", "?"), []).append(a)
        for src, arts in sorted(by_src.items()):
            lines += [f"## {src}", ""]
            for a in arts:
                lines.append(f"- **[{a['title']}]({a['url']})**  ")
                lines.append(f"  *{a.get('published', '')}*")
                lines.append("")

    return "\n".join(lines)


def format_digest_html(data: dict) -> str:
    """Full HTML digest for email."""
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    def _e(s) -> str:
        return html.escape(str(s) if s else "")

    sections = []

    if _is_processed(data):
        for cat in data.get("categories", []):
            arts = cat.get("articles", [])
            if not arts:
                continue
            rows = "".join(
                f'<tr>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #eee;vertical-align:top;'
                f'width:100px;color:#888;font-size:12px;white-space:nowrap;">'
                f'{_e(a.get("source",""))} {_e(a.get("published",""))}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #eee;vertical-align:top;">'
                f'<a href="{_e(a["url"])}" style="color:#2563eb;text-decoration:none;font-weight:500;">{_e(a["title"])}</a>'
                + (f'<br><span style="color:#666;font-size:12px;">{_e(a.get("reason",""))}</span>'
                   if a.get("reason") else "")
                + f'</td></tr>'
                for a in arts
            )
            sections.append(
                f'<h2 style="font-family:sans-serif;font-size:15px;color:#1e293b;'
                f'border-left:3px solid #2563eb;padding-left:10px;margin:24px 0 8px;">{_e(cat["name"])}</h2>'
                f'<table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:14px;">{rows}</table>'
            )
        picks = data.get("ghost_picks", [])
        if picks:
            rows = "".join(
                f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f59e0b30;">'
                f'<a href="{_e(p["url"])}" style="color:#d97706;font-weight:500;text-decoration:none;">{_e(p["title"])}</a>'
                f'<br><span style="color:#666;font-size:12px;">{_e(p.get("source",""))} - {_e(p.get("reason",""))}</span>'
                f'</td></tr>'
                for p in picks
            )
            sections.append(
                f'<h2 style="font-family:sans-serif;font-size:15px;color:#92400e;'
                f'border-left:3px solid #f59e0b;padding-left:10px;margin:24px 0 8px;">✍️ Candidats Ghost</h2>'
                f'<table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:14px;'
                f'background:#fffbeb;border:1px solid #f59e0b40;">{rows}</table>'
            )
        count = sum(len(c.get("articles", [])) for c in data.get("categories", []))
    else:
        articles = data.get("articles", [])
        count = data.get("count", len(articles))
        by_src: dict = {}
        for a in articles:
            by_src.setdefault(a.get("source", "?"), []).append(a)
        for src, arts in sorted(by_src.items()):
            rows = "".join(
                f'<tr><td style="padding:6px 12px;border-bottom:1px solid #eee;font-size:13px;">'
                f'<a href="{_e(a["url"])}" style="color:#2563eb;text-decoration:none;">{_e(a["title"])}</a>'
                f' <span style="color:#999;font-size:12px;">{_e(a.get("published",""))}</span>'
                f'</td></tr>'
                for a in arts
            )
            sections.append(
                f'<h2 style="font-family:sans-serif;font-size:14px;color:#334155;margin:20px 0 4px;">{_e(src)}</h2>'
                f'<table style="width:100%;border-collapse:collapse;font-family:sans-serif;">{rows}</table>'
            )

    body = "\n".join(sections) or "<p style='color:#888;font-family:sans-serif;'>Aucun article.</p>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f8fafc;">
<div style="max-width:800px;margin:0 auto;background:#fff;padding:32px;font-family:sans-serif;">
  <div style="border-bottom:2px solid #2563eb;padding-bottom:12px;margin-bottom:24px;">
    <h1 style="font-size:18px;color:#1e293b;margin:0;">📡 Veille technique</h1>
    <p style="color:#64748b;font-size:13px;margin:4px 0 0;">{now} - {count} articles</p>
  </div>
  {body}
  <div style="border-top:1px solid #e2e8f0;margin-top:32px;padding-top:12px;
              font-size:11px;color:#94a3b8;font-family:sans-serif;">
    OpenClaw veille skill
  </div>
</div>
</body></html>"""


# ---------------------------------------------------------------------------
# OpenClaw config helpers
# ---------------------------------------------------------------------------


def _oc_telegram_token() -> str:
    """Read Telegram bot token from ~/.openclaw/openclaw.json."""
    if not _OC_CONFIG.exists():
        return ""
    try:
        d = json.loads(_OC_CONFIG.read_text(encoding="utf-8"))
        return d.get("channels", {}).get("telegram", {}).get("botToken", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _out_telegram(cfg: dict, data: dict) -> bool:
    """Send to Telegram via Bot API."""
    token = cfg.get("bot_token") or _oc_telegram_token()
    chat_id = str(cfg.get("chat_id", ""))
    if not token:
        print("[dispatch:telegram] bot_token not found - set in output config or configure Telegram in OpenClaw", file=sys.stderr)
        return False
    if not chat_id:
        print("[dispatch:telegram] chat_id required", file=sys.stderr)
        return False

    content = cfg.get("content", "recap")
    text = format_recap(data) if content == "recap" else format_digest_markdown(data)

    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            print("[dispatch:telegram] OK", file=sys.stderr)
            return True
        print(f"[dispatch:telegram] API error: {result.get('description','?')}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[dispatch:telegram] error: {e}", file=sys.stderr)
        return False


def _out_mail(cfg: dict, data: dict) -> bool:
    """Send via mail-client skill CLI, fallback to raw SMTP."""
    mail_to = cfg.get("mail_to", "")
    if not mail_to:
        print("[dispatch:mail-client] mail_to required", file=sys.stderr)
        return False

    now = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    subject = cfg.get("subject", f"Veille tech - {now}")
    content = cfg.get("content", "full_digest")
    body_plain = format_recap(data) if content == "recap" else format_digest_markdown(data)
    body_html  = None if content == "recap" else format_digest_html(data)

    # Try mail-client skill
    mail_script = _SKILLS_DIR / "mail-client" / "scripts" / "mail.py"
    if mail_script.exists():
        cmd = [sys.executable, str(mail_script), "send",
               "--to", mail_to, "--subject", subject, "--body", body_plain]
        if body_html:
            cmd += ["--html", body_html]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                print("[dispatch:mail-client] OK", file=sys.stderr)
                return True
            print(f"[dispatch:mail-client] skill error: {r.stderr[:200]}", file=sys.stderr)
        except Exception as e:
            print(f"[dispatch:mail-client] skill call error: {e}", file=sys.stderr)
        print("[dispatch:mail-client] falling back to SMTP config", file=sys.stderr)

    # SMTP fallback
    return _smtp_fallback(cfg, subject, body_plain, body_html)


def _smtp_fallback(cfg: dict, subject: str, body_plain: str, body_html: str = None) -> bool:
    """Raw SMTP send when mail-client skill is unavailable."""
    import smtplib
    import ssl as _ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import email.utils

    host     = cfg.get("smtp_host", "")
    port     = int(cfg.get("smtp_port", 587))
    user     = cfg.get("smtp_user", "")
    password = cfg.get("smtp_pass", "")
    from_    = cfg.get("mail_from", user)
    to_      = cfg.get("mail_to", "")

    if not all([host, user, password, to_]):
        print("[dispatch:smtp-fallback] missing smtp_host/smtp_user/smtp_pass/mail_to in output config", file=sys.stderr)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"]    = subject
    msg["From"]       = from_
    msg["To"]         = to_
    msg["Date"]       = email.utils.formatdate(localtime=False)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(body_plain, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        ctx = _ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            s.login(user, password)
            s.sendmail(from_, [to_], msg.as_string())
        print("[dispatch:smtp-fallback] OK", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[dispatch:smtp-fallback] error: {e}", file=sys.stderr)
        return False


def _out_nextcloud(cfg: dict, data: dict) -> bool:
    """Write to Nextcloud via nextcloud skill CLI."""
    nc_path = cfg.get("path", "")
    if not nc_path:
        print("[dispatch:nextcloud] path required", file=sys.stderr)
        return False

    content = cfg.get("content", "full_digest")
    text = format_recap(data) if content == "recap" else format_digest_markdown(data)

    nc_script = _SKILLS_DIR / "nextcloud" / "scripts" / "nextcloud.py"
    if not nc_script.exists():
        print(f"[dispatch:nextcloud] skill not installed ({nc_script})", file=sys.stderr)
        return False

    try:
        r = subprocess.run(
            [sys.executable, str(nc_script), "write", nc_path, "--content", text],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            print(f"[dispatch:nextcloud] written to {nc_path} OK", file=sys.stderr)
            return True
        print(f"[dispatch:nextcloud] error: {r.stderr[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[dispatch:nextcloud] error: {e}", file=sys.stderr)
        return False


def _out_file(cfg: dict, data: dict) -> bool:
    """Write digest to a local file."""
    file_path = cfg.get("path", "")
    if not file_path:
        print("[dispatch:file] path required", file=sys.stderr)
        return False

    content = cfg.get("content", "full_digest")
    text = format_recap(data) if content == "recap" else format_digest_markdown(data)

    try:
        p = pathlib.Path(file_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[dispatch:file] written to {p} OK", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[dispatch:file] error: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS = {
    "telegram_bot": _out_telegram,
    "mail-client":  _out_mail,
    "nextcloud":    _out_nextcloud,
    "file":         _out_file,
}

# ---------------------------------------------------------------------------
# Main dispatch function
# ---------------------------------------------------------------------------


def dispatch(data: dict, config: dict, profile: str = None) -> dict:
    """
    Dispatch data to all enabled outputs.
    If profile is given, use config['profiles'][profile] instead of config['outputs'].
    Returns {"ok": [...], "fail": [...], "skip": [...]}.
    """
    if profile:
        outputs = config.get("profiles", {}).get(profile, [])
        if not outputs:
            print(f"[dispatch] profile '{profile}' not found or empty", file=sys.stderr)
    else:
        outputs = config.get("outputs", [])

    results: dict = {"ok": [], "fail": [], "skip": []}

    if not outputs:
        print("[dispatch] No outputs configured. Add 'outputs' to ~/.openclaw/config/veille/config.json", file=sys.stderr)
        return results

    for out in outputs:
        out_type = out.get("type", "")
        if not out.get("enabled", True):
            print(f"[dispatch] {out_type}: skipped (disabled)", file=sys.stderr)
            results["skip"].append(out_type)
            continue
        handler = _HANDLERS.get(out_type)
        if not handler:
            print(f"[dispatch] unknown output type: {out_type!r}", file=sys.stderr)
            results["skip"].append(out_type)
            continue
        ok = handler(out, data)
        results["ok" if ok else "fail"].append(out_type)

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="dispatch.py",
        description="Dispatch a veille digest JSON (stdin) to configured outputs",
    )
    parser.add_argument("--profile", default=None, help="Named output profile")
    args = parser.parse_args()

    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"[dispatch] invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    config: dict = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[dispatch] could not read config: {e}", file=sys.stderr)

    results = dispatch(data, config, profile=args.profile)
    print(json.dumps({"dispatched": results}, ensure_ascii=False, indent=2))

    if results.get("fail"):
        sys.exit(1)


if __name__ == "__main__":
    main()
