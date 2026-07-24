# Reddit Engagement Agent (Human-in-the-Loop)

A starter codebase for monitoring Reddit for posts/comments relevant to your
product, drafting helpful replies with an LLM, and routing every draft
through a **human approval step** before anything is posted.

This intentionally does NOT auto-post without review. That's not a missing
feature — undisclosed, fully-autonomous promotional posting violates
Reddit's rules and tends to backfire hard if discovered. The human review
step is what keeps this both compliant and actually good (a real person
finalizes tone and judgment calls about when to mention your product).

## Architecture

```
Reddit API (PRAW) --fetch & clean-->
  Relevance & decision engine (embeddings + LLM) --drafts reply-->
    LLM response generator -->
      Human review queue (approve / edit / skip) -->
        Posting layer (PRAW) -->
          Reply tracker (watches for replies to your comments, loops back)

Memory store (SQLite) is used throughout: tracks what's been seen,
what's been replied to, and thread context.
```

## Setup

1. Create a Reddit app at https://www.reddit.com/prefs/apps (type: "script").
   Use a **disclosed** account — e.g. bio says "I work on Superflow, happy
   to help" — not an anonymous persona.
2. Copy `.env.example` to `.env` and fill in your credentials.
3. Install [uv](https://docs.astral.sh/uv/) (if you don't have it):
   ```bash
   # Windows (PowerShell)
   irm https://astral.sh/uv/install.ps1 | iex
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
4. Install dependencies (creates a `.venv` and installs from the lockfile):
   ```bash
   uv sync
   ```
5. Initialize the database:
   ```bash
   uv run python db.py
   ```

## Running the pipeline

Run these as separate long-lived processes (or cron jobs). `uv run`
executes each script inside the project's virtual environment:

```bash
# 1. Continuously fetch new posts/comments matching your keywords
uv run python fetch_agent.py

# 2. Continuously score relevance and draft replies for new items
uv run python relevance_agent.py

# 3. Human review dashboard (Streamlit) — approve/edit/reject drafts
uv run streamlit run review_app.py

# 4. Post approved replies to Reddit
uv run python post_agent.py

# 5. Track replies to your own comments, feed them back into review
uv run python reply_tracker.py
```

To add or remove dependencies, use `uv add <pkg>` / `uv remove <pkg>`
(this updates `pyproject.toml` and `uv.lock` automatically).

In practice you'd run 1, 2, 4, 5 as background workers (e.g. via
`supervisord`, systemd, or a simple `while true` loop with sleep — already
built into each script) and keep the Streamlit dashboard open for whoever
is doing review.

## Files

- `config.py` — loads settings from `.env`
- `db.py` — SQLite schema + helper functions (the "memory store")
- `fetch_agent.py` — PRAW monitoring, pushes candidate items into the DB
- `prompts.py` — prompt templates for relevance scoring and drafting
- `relevance_agent.py` — scores relevance, drafts replies, sets status `pending_review`
- `review_app.py` — Streamlit dashboard for human approval
- `post_agent.py` — posts approved replies via PRAW, sets status `posted`
- `reply_tracker.py` — polls for replies to your comments, re-queues them for review

## Notes

- Start with a small, specific keyword list and 2-3 subreddits. Broaden
  once you've seen how the relevance scoring performs.
- Keep posting volume low and organic-looking — a handful of thoughtful
  replies a day beats dozens of generic ones, both for Reddit's spam
  filters and for actually building trust.
- The relevance/drafting prompts in `prompts.py` are a starting point —
  tune them with real examples from your target subreddits.
