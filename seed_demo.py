"""Demo/offline mode — seed the DB with realistic sample Reddit items and run
the relevance + drafting pipeline on them, WITHOUT needing Reddit credentials.

This lets you see the whole system work (score -> draft -> pending_review) using
just the LLM provider (Gemini or Bedrock). Afterwards, open the review dashboard:

    uv run streamlit run review_app.py

Run this with:
    uv run python seed_demo.py
"""
import time

from db import init_db, item_exists, insert_candidate
import relevance_agent as ra

# A handful of realistic posts a Suprflo-relevant agent might surface.
SAMPLE_ITEMS = [
    {
        "reddit_id": "t3_demo1",
        "subreddit": "AI_Agents",
        "author": "demo_user_alex",
        "permalink": "https://reddit.com/r/AI_Agents/demo1",
        "body": (
            "My production agent keeps forgetting everything between sessions. "
            "Users hate re-explaining context every time they come back. How do "
            "people handle long-term memory for agents without it feeling hacky? "
            "Vector stores alone seem unreliable."
        ),
        "matched_keyword": "long-term memory",
    },
    {
        "reddit_id": "t3_demo2",
        "subreddit": "LangChain",
        "author": "demo_user_sam",
        "permalink": "https://reddit.com/r/LangChain/demo2",
        "body": (
            "What's everyone using for persistent memory across conversations in "
            "LangChain? The built-in memory classes lose everything on restart and "
            "rolling my own on top of Postgres is getting painful to maintain."
        ),
        "matched_keyword": "persistent memory",
    },
    {
        "reddit_id": "t3_demo3",
        "subreddit": "MachineLearning",
        "author": "demo_user_jordan",
        "permalink": "https://reddit.com/r/MachineLearning/demo3",
        "body": (
            "Interesting paper on transformer scaling laws for vision models. The "
            "compute-optimal frontier shifts quite a bit vs language. Curious what "
            "people think about the data efficiency claims."
        ),
        "matched_keyword": "context window",  # deliberately low-relevance to Suprflo
    },
    {
        "reddit_id": "t3_demo4",
        "subreddit": "LLMDevs",
        "author": "demo_user_riley",
        "permalink": "https://reddit.com/r/LLMDevs/demo4",
        "body": (
            "Building a customer-support agent and I need it to remember past "
            "tickets per customer. Should I stuff everything into the context "
            "window or is there a cleaner pattern for agent state at scale?"
        ),
        "matched_keyword": "agent state",
    },
]


def seed():
    init_db()
    added = 0
    for it in SAMPLE_ITEMS:
        if item_exists(it["reddit_id"]):
            continue
        insert_candidate(
            reddit_id=it["reddit_id"],
            kind="submission",
            subreddit=it["subreddit"],
            author=it["author"],
            permalink=it["permalink"],
            body=it["body"],
            matched_keyword=it["matched_keyword"],
            thread_root_id=it["reddit_id"],
        )
        added += 1
    print(f"Seeded {added} sample item(s).")


def process_new():
    from db import get_items_by_status

    items = get_items_by_status("new", limit=50)
    print(f"Processing {len(items)} new item(s) with provider="
          f"{ra.settings.LLM_PROVIDER} ...\n")
    for item in items:
        ra.process_item(item)


if __name__ == "__main__":
    seed()
    process_new()
    print(
        "\nDone. Now open the human review dashboard to see the drafts:\n"
        "    uv run streamlit run review_app.py"
    )
