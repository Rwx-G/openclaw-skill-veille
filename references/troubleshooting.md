# Troubleshooting - openclaw-skill-veille

## Common issues

### No articles returned

**Symptoms:** `count: 0` in fetch output, no articles in list.

**Causes and fixes:**

1. **Lookback window too short**: Increase `--hours` value.
   ```bash
   python3 veille.py fetch --hours 72
   ```

2. **All articles already seen**: The seen store may have marked everything. Check:
   ```bash
   python3 veille.py seen-stats
   ```
   Reset if needed:
   ```bash
   rm ~/.openclaw/data/veille/seen_urls.json
   ```

3. **Feed URLs changed**: Some sources change their RSS URL periodically.
   Verify each URL manually in a browser, then update `config.json`.

4. **Network unreachable**: Run `init.py` to test connectivity:
   ```bash
   python3 init.py
   ```

---

### XML parse error / feed silently skipped

**Symptoms:** `[WARN] SourceName: XML parse error: ...` on stderr.

**Causes:** Some feeds serve non-standard XML (e.g., invalid characters, broken CDATA).

**Fix:** These are skipped silently. Remove the problematic source from your config,
or report the issue to the feed provider.

To see all warnings:
```bash
python3 veille.py fetch --hours 24 2>&1 | grep WARN
```

---

### Import error when running veille.py

**Symptoms:** `ModuleNotFoundError: No module named 'seen_store'`

**Cause:** Python cannot find the sibling modules.

**Fix:** Always run `veille.py` with its full path, or from the `scripts/` directory:
```bash
cd ~/dev/openclaw-skill-veille/scripts
python3 veille.py fetch

# OR with full path (works from anywhere):
python3 ~/dev/openclaw-skill-veille/scripts/veille.py fetch
```

---

### Config not found

**Symptoms:** `[INFO] Using config.example.json` or `[WARN] Could not read config`

**Fix:** Run setup first:
```bash
python3 ~/dev/openclaw-skill-veille/scripts/setup.py
```

---

### Topic filter removes too many articles

**Symptoms:** `skipped_topic` count is very high, important articles missing.

**Cause:** The Jaccard similarity threshold (0.40) may be too aggressive for your use case.

**Fix:** Raise the threshold in config.json:
```json
{
  "topic_similarity_threshold": 0.55
}
```

Note: `topic_similarity_threshold` in config.json is read by veille.py but the
hardcoded value in `topic_filter.py` (`TOPIC_SIMILARITY_THRESHOLD = 0.40`) is the
module default. veille.py passes the config value to `TopicStore` correctly.

---

### Seen URL store grows too large

**Symptoms:** `seen-stats` shows thousands of entries; old articles resurface.

**Fix:** The store auto-purges entries older than `seen_url_ttl_days` (default 14 days)
on every load. If you want a shorter TTL, update config.json:
```json
{
  "seen_url_ttl_days": 7
}
```

Or manually clear the store:
```bash
rm ~/.openclaw/data/veille/seen_urls.json
```

---

### A feed uses Atom but articles are not parsed

**Symptoms:** Feed fetched (no WARN) but 0 articles returned.

**Cause:** Some Atom feeds use non-standard namespace prefixes.

**Debug:** Check what the feed returns:
```bash
curl -s "https://example.com/feed.xml" | head -50
```

Look for the root element: `<feed>`, `<atom:feed>`, or `<rss>`.
If the root uses a custom namespace prefix, the parser may miss the entries.
This is a known limitation of the v1 parser.

---

### CERT-FR feed returns 0 articles

**Symptoms:** CERT-FR shows 0 articles even with `--hours 168` (7 days).

**Cause:** CERT-FR publishes advisories infrequently. This is normal behavior.
Try with a longer window:
```bash
python3 veille.py fetch --hours 720  # 30 days
```

---

## Debugging tips

**See all fetch activity:**
```bash
python3 veille.py fetch --hours 24 2>&1 | tee /tmp/veille-debug.log
```

**Test a single feed manually:**
```python
from scripts.veille import fetch_feed
articles = fetch_feed("Test", "https://example.com/feed.rss", hours=24, max_articles=5)
for a in articles:
    print(a["title"])
```

**Test topic similarity between two titles:**
```bash
cd ~/dev/openclaw-skill-veille/scripts
python3 topic_filter.py --test "Fortinet RCE vulnerability CVE-2024-1234" "Critical flaw in Fortinet CVE-2024-1234 allows remote code execution"
```

**Reset all stores:**
```bash
rm -f ~/.openclaw/data/veille/seen_urls.json
rm -f ~/.openclaw/data/veille/topic_seen.json
```
