"""Watches replies to our own posted comments and feeds new ones back into
the review queue (status='new'), so they go through the same
relevance -> draft -> human review -> post pipeline as everything else.

Run as a long-lived process:
    python reply_tracker.py
"""
import time

from config import settings
from db import init_db, get_our_posted_comment_ids, item_exists, insert_candidate
from reddit_client import get_reddit


def check_replies(reddit):
    our_comment_ids = get_our_posted_comment_ids()
    found = 0

    for our_id in our_comment_ids:
        raw_id = our_id.split("_", 1)[1]
        try:
            comment = reddit.comment(id=raw_id)
            comment.refresh()  # loads .replies
        except Exception as e:
            print(f"[reply_tracker] couldn't refresh {our_id}: {e}")
            continue

        for reply in comment.replies:
            reddit_id = f"t1_{reply.id}"
            if item_exists(reddit_id):
                continue
            if str(reply.author) == settings.REDDIT_USERNAME:
                continue  # skip our own replies in the thread

            insert_candidate(
                reddit_id=reddit_id,
                kind="comment",
                subreddit=str(comment.subreddit),
                author=str(reply.author),
                permalink=f"https://reddit.com{reply.permalink}",
                body=reply.body,
                matched_keyword="[reply to our comment]",
                is_reply_to_us=True,
                parent_our_comment_id=our_id,
                thread_root_id=f"t3_{comment.submission.id}",
            )
            found += 1

    return found


def main():
    init_db()
    reddit = get_reddit()
    while True:
        try:
            found = check_replies(reddit)
            if found:
                print(f"Found {found} new reply(ies) to our comments.")
        except Exception as e:
            print(f"[reply_tracker] error: {e}")
        time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
