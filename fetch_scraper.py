"""No-credentials alternative to fetch_agent.py, using Reddit's public RSS feeds.

Reddit still serves public RSS feeds (e.g. reddit.com/r/<sub>/new/.rss) even
where the .json API is blocked, and RSS is a legitimate public-feed mechanism.
This reads new SUBMISSIONS per target subreddit, matches your keywords, and
inserts matches into the DB exactly like fetch_agent.py — so relevance scoring,
drafting, and human review all work unchanged, with NO Reddit credentials.

Notes / limits:
  * Fetches new submissions (posts). Subreddit-wide comment streams aren't
    reliably available via RSS, so this covers posts, not comments.
  * Keep polling gentle — Reddit rate-limits RSS too (HTTP 429 if hammered).
  * Posting replies and tracking replies are done MANUALLY by you on reddit.com.

Run as a long-lived process:
    uv run python fetch_scraper.py
"""
import re
import time
from html import unescape

import feedparser
import requests

from config import settings
from db import init_db, item_exists, insert_candidate

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
# Reddit rate-limits RSS aggressively per IP — a big gap between subreddits
# avoids HTTP 429. Any subreddit that still 429s is simply retried next cycle.
REQUEST_PAUSE_SECONDS = 12

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html: str) -> str:
    """Turn RSS HTML content into plain text for the LLM."""
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def matched_keyword(text: str) -> str | None:
    text_lower = text.lower()
    for kw in settings.TARGET_KEYWORDS:
        if kw.lower() in text_lower:
            return kw
    return None


def fetch_feed(sub_name: str):
    """Return parsed RSS entries for a subreddit's new posts, or [] on block."""
    url = f"https://www.reddit.com/r/{sub_name}/new/.rss?limit=25"
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    except Exception as e:
        print(f"[fetch_scraper] request failed for r/{sub_name}: {e}")
        return []
    if resp.status_code != 200:
        note = ""
        if resp.status_code in (403, 429):
            note = " (rate-limited/blocked — slow down or try later)"
        print(f"[fetch_scraper] r/{sub_name}: HTTP {resp.status_code}{note}")
        return []
    return feedparser.parse(resp.content).entries


def poll_once():
    found = 0
    for sub_name in settings.TARGET_SUBREDDITS:
        for entry in fetch_feed(sub_name):
            # Reddit Atom id looks like "t3_abc123"; fall back to parsing the link.
            reddit_id = entry.get("id", "")
            if not reddit_id.startswith("t3_"):
                # e.g. link .../comments/abc123/title/ -> t3_abc123
                parts = entry.get("link", "").split("/comments/")
                if len(parts) == 2:
                    reddit_id = "t3_" + parts[1].split("/")[0]
            if not reddit_id.startswith("t3_"):
                continue
            if item_exists(reddit_id):
                continue

            title = entry.get("title", "")
            # `content` holds the post body as HTML; `summary` is a fallback.
            body_html = ""
            if entry.get("content"):
                body_html = entry["content"][0].get("value", "")
            body_html = body_html or entry.get("summary", "")
            text = f"{title}\n{strip_html(body_html)}".strip()

            kw = matched_keyword(text)
            if not kw:
                continue

            author = entry.get("author", "").lstrip("/u/").lstrip("u/") or "unknown"
            insert_candidate(
                reddit_id=reddit_id,
                kind="submission",
                subreddit=sub_name,
                author=author,
                permalink=entry.get("link", ""),
                body=text.strip(),
                matched_keyword=kw,
                thread_root_id=reddit_id,
            )
            found += 1
        time.sleep(REQUEST_PAUSE_SECONDS)
    return found


def main():
    init_db()
    print(f"Scraping via RSS: {settings.TARGET_SUBREDDITS}")
    print(f"Keywords: {settings.TARGET_KEYWORDS}")
    while True:
        try:
            found = poll_once()
            if found:
                print(f"Found {found} new candidate item(s).")
            else:
                print("No new keyword matches this cycle.")
        except Exception as e:
            print(f"[fetch_scraper] error: {e}")
        time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
