---
name: veille
description: "RSS feed aggregator and deduplication engine for OpenClaw agents. Use when: fetching recent articles from configured news sources, filtering already-seen articles, deduplicating articles covering the same topic. NOT for: sending emails (use mail-client), saving to Nextcloud (use nextcloud-files), LLM scoring (handled by the agent)."
homepage: https://github.com/Rwx-G/openclaw-skill-veille
compatibility: Python 3.9+ - no external dependencies (stdlib only) - network access to RSS feeds
metadata:
  {
    "openclaw": {
      "emoji": "📰",
      "requires": { "env": [] },
      "primaryEnv": ""
    }
  }
ontology:
  reads: [rss_feeds]
  writes: [local_data_files]
---

# Skill Veille - RSS Aggregator

RSS feed aggregator with URL deduplication and topic-based deduplication for OpenClaw agents.
Fetches articles from 20+ configured sources, filters already-seen URLs (TTL 14 days),
and deduplicates articles covering the same story using Jaccard similarity + named entities.

No external dependencies: stdlib Python only (urllib, xml.etree, email.utils).

---

## Trigger phrases

- "fais une veille"
- "quoi de neuf en securite / tech / crypto / IA ?"
- "donne-moi les news du jour"
- "articles recents sur [sujet]"
- "veille RSS"
- "digest du matin"
- "nouvelles non vues"

---

## Quick Start

```bash
# 1. Setup
python3 ~/dev/openclaw-skill-veille/scripts/setup.py

# 2. Validate
python3 ~/dev/openclaw-skill-veille/scripts/init.py

# 3. Fetch
python3 ~/dev/openclaw-skill-veille/scripts/veille.py fetch --hours 24 --filter-seen --filter-topic
```

---

## Setup

### Requirements

- Python 3.9+
- Network access to RSS feeds (public, no auth required)
- No pip installs needed

### Installation

```bash
# Clone or copy the skill directory
cd ~/dev/openclaw-skill-veille

# Run setup wizard
python3 scripts/setup.py

# Validate
python3 scripts/init.py
```

The wizard creates:
- `~/.openclaw/config/veille/config.json` (from `config.example.json`)
- `~/.openclaw/data/veille/` (data directory)

### Customizing sources

Edit `~/.openclaw/config/veille/config.json` and add/remove entries in the `"sources"` dict:

```json
{
  "sources": {
    "My Blog": "https://example.com/feed.xml",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/"
  }
}
```

---

## Storage and credentials

| Path | Written by | Purpose | Contains secrets |
|------|-----------|---------|-----------------|
| `~/.openclaw/config/veille/config.json` | `setup.py` | Sources RSS, seuils, options | NO |
| `~/.openclaw/data/veille/seen_urls.json` | `veille.py` | URLs deja presentees (TTL 14j) | NO |
| `~/.openclaw/data/veille/topic_seen.json` | `veille.py` | Sujets deja couverts (TTL 5j) | NO |

This skill has **no credentials** - all RSS feeds are public.

### Cleanup on uninstall

```bash
rm -rf ~/.openclaw/config/veille
rm -rf ~/.openclaw/data/veille
```

---

## CLI reference

### `fetch`

```
python3 veille.py fetch [--hours N] [--filter-seen] [--filter-topic] [--sources FILE]
```

Options:
- `--hours N` : lookback window in hours (default: from config, usually 24)
- `--filter-seen` : filter already-seen URLs (uses seen_urls.json TTL store)
- `--filter-topic` : deduplicate by topic (uses topic_seen.json + Jaccard similarity)
- `--sources FILE` : path to custom JSON sources file

Output (JSON on stdout):
```json
{
  "hours": 24,
  "count": 42,
  "skipped_url": 5,
  "skipped_topic": 3,
  "articles": [...],
  "wrapped_listing": "=== UNTRUSTED EXTERNAL CONTENT ..."
}
```

### `seen-stats`

```
python3 veille.py seen-stats
```

Shows URL seen store statistics (count, TTL, file path).

### `topic-stats`

```
python3 veille.py topic-stats
```

Shows topic deduplication store statistics.

### `mark-seen`

```
python3 veille.py mark-seen URL [URL ...]
```

Marks one or more URLs as already seen (prevents them from appearing in future fetches with `--filter-seen`).

### `config`

```
python3 veille.py config
```

Prints the active configuration (no secrets).

---

## Templates (agent usage)

### Basic digest

```python
# In agent tool call:
result = exec("python3 ~/dev/openclaw-skill-veille/scripts/veille.py fetch --hours 24 --filter-seen --filter-topic")
data = json.loads(result.stdout)
# data["wrapped_listing"] is ready for LLM prompt injection
# data["count"] = number of new articles
# data["articles"] = list of article dicts
```

### Prompt template

```
You are a news analyst. Here are today's articles:

{data["wrapped_listing"]}

Please summarize the 5 most important stories, focusing on security and tech.
```

### Agent workflow example

```
1. Call veille fetch --filter-seen --filter-topic
2. If count > 0: pass wrapped_listing to LLM for analysis
3. LLM produces digest summary
4. Optionally: send digest via mail-client skill
5. Optionally: save to Nextcloud via nextcloud-files skill
```

### Filtering by keyword (post-fetch)

```python
data = json.loads(fetch_output)
security_articles = [
    a for a in data["articles"]
    if any(kw in a["title"].lower() for kw in ["cve", "vuln", "patch", "breach"])
]
```

---

## Ideas

- Add keyword-based filtering (`--keywords security,cve,linux`)
- Add per-source TTL override in config
- Export digest as HTML or Markdown
- Schedule with cron: `0 8 * * * python3 veille.py fetch --filter-seen --filter-topic`
- Weight articles by source tier for LLM prioritization
- Add OPML import/export for source list management
- Integrate with ntfy or Telegram for real-time alerts on high-priority articles

---

## Combine with

- **mail-client** : send the digest by email after fetching
  ```
  veille fetch --filter-seen | ... | mail-client send
  ```

- **nextcloud-files** : archive the daily digest as a Markdown file
  ```
  veille fetch --filter-seen | jq .wrapped_listing -r > /tmp/digest.md
  nextcloud-files upload /tmp/digest.md /Digests/$(date +%Y-%m-%d).md
  ```

---

## Troubleshooting

See `references/troubleshooting.md` for detailed troubleshooting steps.

Common issues:

- **No articles returned**: check `--hours` value, verify feed URLs in config
- **XML parse error on a feed**: some feeds use non-standard XML; the skill skips broken items silently
- **All articles filtered as seen**: run `seen-stats` to check store size; reset with `rm seen_urls.json`
- **Import error**: ensure you run `veille.py` from its directory or via full path
