"""Read-only fetch of public Reddit posts via Reddit's public RSS feeds.

Reddit still serves public RSS feeds (e.g. reddit.com/r/<sub>/new/.rss) even
where the .json API is blocked, and RSS is a legitimate public-feed mechanism.
This reads new SUBMISSIONS and COMMENTS per target subreddit, PLUS a Reddit-wide
keyword SEARCH feed, matches your keywords, and inserts matches into the DB —
so relevance scoring, drafting, and human review all work with NO Reddit
credentials and no login. This is the only fetch path; nothing here writes to
Reddit.

What it covers (Tier-1 upgraded):
  * New submissions per subreddit ............ /r/<sub>/new/.rss
  * New comments per subreddit ............... /r/<sub>/comments/.rss
  * Reddit-WIDE keyword search (all subs) .... /search.rss?q=...
  * Whole-word keyword matching (no more "RAG" matching "sto[rag]e").

Notes / limits:
  * Keep polling gentle — Reddit rate-limits RSS too (HTTP 429 if hammered).
    We pause between requests and back off on 429.
  * Posting replies and tracking replies are done MANUALLY by you on reddit.com.

Run as a long-lived process:
    uv run python fetch_scraper.py
"""
import random
import re
import time
from html import unescape
from urllib.parse import quote

import feedparser
import requests

from config import settings
from db import init_db, item_exists, insert_candidate

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
# Reddit rate-limits RSS aggressively per IP. We pause (with jitter) between
# requests; any feed that 429s is skipped and simply retried next cycle.
# NOTE: we do NOT retry a 429 immediately — once Reddit throttles your IP,
# retrying just gets throttled again and wastes minutes. Skip and move on.
REQUEST_PAUSE_SECONDS = 6
REQUEST_JITTER_SECONDS = 4  # add 0..N random seconds so the pattern is less bot-like
# Max chars for a single OR-joined search query (Reddit caps query length).
SEARCH_QUERY_MAX_LEN = 450

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html: str) -> str:
    """Turn RSS HTML content into plain text for the LLM."""
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def compile_patterns():
    """Whole-word regex per keyword. Rebuilt each poll so UI keyword edits apply.

    Word boundaries stop 'RAG' from matching 'storage'/'average'/'fragment'.
    """
    patterns = []
    for kw in settings.TARGET_KEYWORDS:
        patterns.append((kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)))
    return patterns


def matched_keyword(text: str, patterns) -> str | None:
    for kw, pat in patterns:
        if pat.search(text):
            return kw
    return None


def build_search_queries(keywords, max_len: int = SEARCH_QUERY_MAX_LEN):
    """Batch keywords into OR-joined quoted queries within Reddit's length cap.

    One request like  ("agent memory" OR "long-term memory" OR ...)  searches
    ALL of Reddit for any of the keywords, instead of one request per keyword.
    """
    queries, current = [], []
    for kw in keywords:
        term = f'"{kw}"'
        candidate = " OR ".join(current + [term])
        if current and len(candidate) > max_len:
            queries.append(" OR ".join(current))
            current = [term]
        else:
            current.append(term)
    if current:
        queries.append(" OR ".join(current))
    return queries


def polite_pause():
    """Sleep between requests, with jitter, to stay under Reddit's RSS throttle."""
    time.sleep(REQUEST_PAUSE_SECONDS + random.uniform(0, REQUEST_JITTER_SECONDS))


def fetch_feed(url: str, label: str):
    """GET an RSS/Atom URL and return parsed entries, or [] on block/error.

    On 429 we DON'T retry — a throttled IP stays throttled, so we skip this
    feed and pick it up next cycle. This keeps a fetch from hanging for minutes.
    """
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    except Exception as e:
        print(f"[fetch_scraper] request failed for {label}: {e}")
        return []
    if resp.status_code == 200:
        return feedparser.parse(resp.content).entries
    note = " (rate-limited — will retry next cycle)" if resp.status_code in (403, 429) else ""
    print(f"[fetch_scraper] {label}: HTTP {resp.status_code}{note}")
    return []


def extract_ids(entry):
    """Return (reddit_id, kind, thread_root_id) from an Atom entry.

    Submissions have id 't3_...', comments 't1_...'. thread_root_id is always
    the parent post's 't3_...' (parsed from the permalink for comments).
    """
    rid = entry.get("id", "")
    link = entry.get("link", "")
    if rid.startswith("t1_"):
        kind = "comment"
    elif rid.startswith("t3_"):
        kind = "submission"
    else:
        # Fall back to the permalink: .../comments/<postid>/... -> t3_<postid>
        parts = link.split("/comments/")
        if len(parts) == 2:
            rid = "t3_" + parts[1].split("/")[0]
            kind = "submission"
        else:
            return "", "", ""
    thread_root = rid
    if "/comments/" in link:
        thread_root = "t3_" + link.split("/comments/")[1].split("/")[0]
    return rid, kind, thread_root


def extract_subreddit(entry, fallback: str) -> str:
    """Subreddit name from the permalink (needed for Reddit-wide search hits)."""
    link = entry.get("link", "")
    if "/r/" in link:
        return link.split("/r/")[1].split("/")[0]
    return fallback or "unknown"


def process_entry(entry, patterns, source_sub, seen) -> int:
    """Match one entry against keywords and insert it as a candidate. Returns 1 if added."""
    reddit_id, kind, thread_root = extract_ids(entry)
    if not reddit_id or reddit_id in seen or item_exists(reddit_id):
        return 0

    title = entry.get("title", "")
    body_html = ""
    if entry.get("content"):
        body_html = entry["content"][0].get("value", "")
    body_html = body_html or entry.get("summary", "")
    text = f"{title}\n{strip_html(body_html)}".strip()

    # Require our OWN whole-word keyword match — for search hits too. Reddit's
    # search matches loosely on single common words, so trusting it floods the
    # queue with junk that still costs an LLM call to skip. Drop non-matches.
    kw = matched_keyword(text, patterns)
    if not kw:
        return 0

    subreddit = source_sub or extract_subreddit(entry, "unknown")
    author = (entry.get("author", "") or "").lstrip("/u/").lstrip("u/") or "unknown"
    insert_candidate(
        reddit_id=reddit_id,
        kind=kind,
        subreddit=subreddit,
        author=author,
        permalink=entry.get("link", ""),
        body=text,
        matched_keyword=kw,
        thread_root_id=thread_root,
    )
    seen.add(reddit_id)
    return 1


def poll_once(deep: bool = False):
    """One fetch pass. Keep it light so Reddit doesn't throttle (HTTP 429).

    deep=False (default): reddit-wide search + per-subreddit NEW POSTS  (~9 requests)
    deep=True           : also pulls per-subreddit NEW COMMENTS         (~17 requests)

    Comments feeds double the request count and are the biggest 429 risk, so
    they're opt-in. The reddit-wide search is the single highest-value feed
    (all keywords across all of Reddit), so it runs first.
    """
    patterns = compile_patterns()
    seen: set[str] = set()
    found = 0

    # 1) Reddit-WIDE keyword search — one OR-query covers many keywords and
    #    catches relevant threads even in subreddits you didn't list.
    #    Only multi-word phrases are searched: single words like "RAG"/"mem0"
    #    match far too loosely across all of Reddit (r/Shihtzu, r/cna, ...).
    #    Single words still match within the per-subreddit feeds below.
    search_terms = [k for k in settings.TARGET_KEYWORDS if " " in k]
    for query in build_search_queries(search_terms):
        url = f"https://www.reddit.com/search.rss?q={quote(query)}&sort=new&limit=25"
        entries = fetch_feed(url, "reddit-wide search")
        for entry in entries:
            found += process_entry(entry, patterns, None, seen)
        polite_pause()

    # 2) Per-subreddit NEW POSTS (and comments only when deep=True).
    feeds = [("posts", "new")]
    if deep:
        feeds.append(("comments", "comments"))
    for sub_name in settings.TARGET_SUBREDDITS:
        for feed_kind, path in feeds:
            url = f"https://www.reddit.com/r/{sub_name}/{path}/.rss?limit=25"
            entries = fetch_feed(url, f"r/{sub_name} {feed_kind}")
            for entry in entries:
                found += process_entry(entry, patterns, sub_name, seen)
            polite_pause()

    return found


def main():
    init_db()
    print(f"Scraping via RSS (reddit-wide search + posts + comments): {settings.TARGET_SUBREDDITS}")
    print(f"Keywords: {settings.TARGET_KEYWORDS}")
    while True:
        try:
            # The long-running background process can afford the deep pass.
            found = poll_once(deep=True)
            if found:
                print(f"Found {found} new candidate item(s).")
            else:
                print("No new keyword matches this cycle.")
        except Exception as e:
            print(f"[fetch_scraper] error: {e}")
        time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
