"""Polls target subreddits for new posts/comments matching target keywords
and inserts candidates into the database with status='new'.

Run as a long-lived process:
    python fetch_agent.py
"""
import time

from config import settings
from db import init_db, item_exists, insert_candidate
from reddit_client import get_reddit


def matched_keyword(text: str) -> str | None:
    text_lower = text.lower()
    for kw in settings.TARGET_KEYWORDS:
        if kw.lower() in text_lower:
            return kw
    return None


def poll_once(reddit):
    found = 0
    for sub_name in settings.TARGET_SUBREDDITS:
        subreddit = reddit.subreddit(sub_name)

        # New submissions
        for submission in subreddit.new(limit=25):
            reddit_id = f"t3_{submission.id}"
            if item_exists(reddit_id):
                continue
            text = f"{submission.title}\n{submission.selftext or ''}"
            kw = matched_keyword(text)
            if not kw:
                continue
            insert_candidate(
                reddit_id=reddit_id,
                kind="submission",
                subreddit=sub_name,
                author=str(submission.author),
                permalink=f"https://reddit.com{submission.permalink}",
                body=text.strip(),
                matched_keyword=kw,
                thread_root_id=reddit_id,
            )
            found += 1

        # New comments
        for comment in subreddit.comments(limit=100):
            reddit_id = f"t1_{comment.id}"
            if item_exists(reddit_id):
                continue
            kw = matched_keyword(comment.body)
            if not kw:
                continue
            insert_candidate(
                reddit_id=reddit_id,
                kind="comment",
                subreddit=sub_name,
                author=str(comment.author),
                permalink=f"https://reddit.com{comment.permalink}",
                body=comment.body,
                matched_keyword=kw,
                thread_root_id=f"t3_{comment.submission.id}",
            )
            found += 1

    return found


def main():
    init_db()
    reddit = get_reddit()
    print(f"Monitoring: {settings.TARGET_SUBREDDITS}")
    print(f"Keywords: {settings.TARGET_KEYWORDS}")
    while True:
        try:
            found = poll_once(reddit)
            if found:
                print(f"Found {found} new candidate item(s).")
        except Exception as e:
            print(f"[fetch_agent] error: {e}")
        time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
