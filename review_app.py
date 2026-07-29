"""Human review dashboard.

Run with:
    streamlit run review_app.py

Shows every item with status='pending_review', lets a human read the
original post/comment, edit the drafted reply, and approve/reject/skip.
Only 'approved' items get posted (by post_agent.py).
"""
import time

import streamlit as st

from config import settings
from db import init_db, get_items_by_status, update_item

st.set_page_config(page_title="Reddit Reply Review", layout="wide")
init_db()

st.title("Reddit reply review queue")
st.caption(
    "Every reply goes live only after a human approves it here. "
    "Edit freely before approving — the final_reply is what gets posted."
)


def parse_keywords(text: str) -> list[str]:
    return [k.strip() for k in text.split(",") if k.strip()]


def fetch_and_score(keywords):
    """Fetch new posts via RSS and score/draft them — the whole input pipeline."""
    import fetch_scraper
    import relevance_agent

    # Override the keyword list for this fetch with whatever the UI has.
    settings.TARGET_KEYWORDS = keywords
    found = fetch_scraper.poll_once()
    new_items = get_items_by_status("new", limit=200)
    for it in new_items:
        relevance_agent.process_item(it)
    return found, len(new_items)


# Prefill the keyword editor with the keywords from .env on first load.
if "keywords_text" not in st.session_state:
    st.session_state["keywords_text"] = ", ".join(settings.TARGET_KEYWORDS)

st.markdown("**Target keywords** — edit or add (comma-separated). Used when you fetch.")
st.text_area(
    "Target keywords",
    key="keywords_text",
    height=90,
    label_visibility="collapsed",
)

col1, col2 = st.columns([1, 3])
with col1:
    if st.button("🔄 Fetch & score new posts", type="primary", use_container_width=True):
        keywords = parse_keywords(st.session_state["keywords_text"])
        if not keywords:
            st.warning("Add at least one keyword before fetching.")
        else:
            with st.spinner(
                "Fetching from Reddit and scoring with the LLM… "
                "this can take 1–2 minutes (Reddit rate-limits RSS, so we go slowly)."
            ):
                found, scored = fetch_and_score(keywords)
            st.session_state["last_fetch"] = (
                f"Fetched {found} new post(s); scored {scored} using "
                f"{len(keywords)} keyword(s). Relevant ones (score ≥ 5) shown below."
            )
with col2:
    if st.session_state.get("last_fetch"):
        st.success(st.session_state["last_fetch"])

items = get_items_by_status("pending_review", limit=50, order="DESC")

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
