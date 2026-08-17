"""Regenerate drafts for items already in the review queue.

When you tune the drafting prompt (prompts.DRAFT_SYSTEM_PROMPT), items that were
already drafted keep their OLD text — the fetch button never re-drafts existing
items. Run this once to refresh every pending_review draft with the current
prompt/voice:

    python redraft_queue.py

Only touches status='pending_review'; scores and statuses are left alone.
"""
import time

from db import init_db, get_items_by_status, update_item
from relevance_agent import draft_reply


def main():
    init_db()
    items = get_items_by_status("pending_review", limit=500)
    total = len(items)
    print(f"Re-drafting {total} pending_review item(s) with the current prompt...\n")

    for i, item in enumerate(items, 1):
        rid = item["reddit_id"]
        should_mention = bool(item.get("should_mention_product"))
        try:
            new_draft = draft_reply(item, should_mention)
        except Exception as e:
            print(f"[{i}/{total}] {rid}: FAILED ({e}) — left unchanged")
            continue
        update_item(rid, draft_reply=new_draft)
        preview = new_draft.replace("\n", " ")[:70]
        print(f"[{i}/{total}] {rid}: {preview}...")
        # Gentle pacing so we don't hammer the model endpoint back-to-back.
        time.sleep(1)

    print(f"\nDone. Refreshed {total} draft(s).")


if __name__ == "__main__":
    main()
