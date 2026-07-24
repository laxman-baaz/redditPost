"""Posts items with status='approved' to Reddit, then marks them 'posted'.

Run as a long-lived process:
    python post_agent.py

Deliberately only touches items a human has already approved in
review_app.py. Nothing in this file makes the "should we post?" decision.
"""
import time

from config import settings
from db import init_db, get_items_by_status, update_item
from reddit_client import get_reddit


def strip_prefix(reddit_id: str) -> str:
    return reddit_id.split("_", 1)[1]


def post_item(reddit, item: dict):
    reply_text = item.get("final_reply") or item.get("draft_reply")
    if not reply_text:
        print(f"[post_agent] no reply text for {item['reddit_id']}, skipping")
        return

    raw_id = strip_prefix(item["reddit_id"])
    try:
        if item["kind"] == "submission":
            target = reddit.submission(id=raw_id)
        else:
            target = reddit.comment(id=raw_id)

        posted = target.reply(reply_text)

        update_item(
            item["reddit_id"],
            status="posted",
            posted_comment_id=f"t1_{posted.id}",
            posted_at=int(time.time()),
        )
        print(f"Posted reply to {item['reddit_id']} -> t1_{posted.id}")
    except Exception as e:
        print(f"[post_agent] failed to post reply to {item['reddit_id']}: {e}")


def main():
    init_db()
    reddit = get_reddit()
    while True:
        items = get_items_by_status("approved", limit=10)
        for item in items:
            post_item(reddit, item)
            # Small pause between posts to keep a natural, non-bulk posting
            # cadence rather than firing several replies back-to-back.
            time.sleep(15)
        time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
