"""Human review dashboard.

Run with:
    streamlit run review_app.py

Shows every item with status='pending_review', lets a human read the
original post/comment, edit the drafted reply, and approve/reject/skip.
Only 'approved' items get posted (by post_agent.py).
"""
import time

import streamlit as st

from db import init_db, get_items_by_status, update_item

st.set_page_config(page_title="Reddit Reply Review", layout="wide")
init_db()

st.title("Reddit reply review queue")
st.caption(
    "Every reply goes live only after a human approves it here. "
    "Edit freely before approving — the final_reply is what gets posted."
)

items = get_items_by_status("pending_review", limit=50)

if not items:
    st.info("No items pending review right now.")
else:
    st.write(f"{len(items)} item(s) waiting for review")

for item in items:
    with st.container(border=True):
        cols = st.columns([3, 2])

        with cols[0]:
            st.markdown(f"**r/{item['subreddit']}** · matched: `{item['matched_keyword']}`")
            if item.get("is_reply_to_us"):
                st.markdown(":speech_balloon: *This is a reply to one of our comments.*")
            st.text_area(
                "Original post/comment",
                value=item["body"],
                height=150,
                disabled=True,
                key=f"body_{item['reddit_id']}",
            )
            st.markdown(f"[View on Reddit]({item['permalink']})")

        with cols[1]:
            st.markdown(
                f"**Relevance score:** {item.get('relevance_score', 'n/a')}/10  \n"
                f"**Mention product?** {'Yes' if item.get('should_mention_product') else 'No'}"
            )
            st.caption(item.get("relevance_reasoning", ""))

            edited_reply = st.text_area(
                "Draft reply (edit before approving)",
                value=item.get("draft_reply", ""),
                height=180,
                key=f"draft_{item['reddit_id']}",
            )

            btn_cols = st.columns(3)
            if btn_cols[0].button("Approve", key=f"approve_{item['reddit_id']}", type="primary"):
                update_item(
                    item["reddit_id"],
                    final_reply=edited_reply,
                    status="approved",
                    reviewed_at=int(time.time()),
                )
                st.rerun()

            if btn_cols[1].button("Reject", key=f"reject_{item['reddit_id']}"):
                update_item(
                    item["reddit_id"],
                    status="rejected",
                    reviewed_at=int(time.time()),
                )
                st.rerun()

            if btn_cols[2].button("Skip for now", key=f"skip_{item['reddit_id']}"):
                st.info("Left in queue — refresh later.")
