# Reddit Engagement Assistant (Read-Only, Human-in-the-Loop)

A tool for monitoring Reddit for posts/comments relevant to your product,
drafting helpful replies with an LLM, and routing every draft through a
**human review step**. You then post the approved replies **yourself**, as a
normal Reddit user.

**This is read-only.** It never logs in to Reddit and never posts anything
automatically. It reads public posts through Reddit's public RSS feeds (no
API app, no credentials, no bot account) and hands you finished drafts to
review. A human copies each approved reply and posts it manually. This keeps
the tool firmly on the right side of Reddit's rules — undisclosed,
fully-autonomous promotional posting violates them and tends to backfire.

> **Reviewing this for a Reddit data-access request?** See
> [WHAT_THIS_DOES.md](WHAT_THIS_DOES.md) for a concise, read-only summary of
> exactly what the tool does and doesn't do.

## Architecture

```
Reddit public RSS feeds --fetch & clean-->
  Relevance & decision engine (LLM) --scores + drafts reply-->
    Human review queue (approve / edit / reject) -->
      "Approved — ready to post" list --copy & post manually as yourself-->

Memory store (SQLite) is used throughout: tracks what's been seen,
scored, drafted, and reviewed so nothing is processed twice.
```

## Setup

No Reddit account or API credentials are required.

1. Copy `.env.example` to `.env` and fill in your **LLM** settings
   (Gemini API key, or AWS Bedrock via your AWS CLI credentials) plus your
   product info and target keywords/subreddits.
2. Install [uv](https://docs.astral.sh/uv/) (if you don't have it):
   ```bash
   # Windows (PowerShell)
   irm https://astral.sh/uv/install.ps1 | iex
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Install dependencies (creates a `.venv` and installs from the lockfile):
   ```bash
   uv sync
   ```
4. Initialize the database:
   ```bash
   uv run python db.py
   ```

## Running

Everything runs from the Streamlit dashboard — fetch, score, draft, review,
and grab approved replies to post yourself:

```bash
uv run streamlit run review_app.py
```

In the dashboard:
1. Edit the target keywords, then click **Fetch & score new posts**. This
   pulls matching public posts via RSS and scores/drafts them.
2. Review each draft in the queue — edit freely, then **Approve** / **Reject**.
3. Scroll to **Approved — ready to post manually**: copy each reply, open the
   thread on Reddit, post it as yourself, and click **Mark as posted**.

### Utilities

```bash
# Re-draft every item already in the review queue with the current prompt
# (run after you tune prompts.py — existing drafts don't auto-refresh)
uv run python redraft_queue.py
```

To add or remove dependencies, use `uv add <pkg>` / `uv remove <pkg>`
(this updates `pyproject.toml` and `uv.lock` automatically).

## Files

- `config.py` — loads settings from `.env`
- `db.py` — SQLite schema + helper functions (the "memory store")
- `fetch_scraper.py` — read-only fetch of public posts via Reddit RSS feeds
- `prompts.py` — prompt templates for relevance scoring and drafting
- `relevance_agent.py` — scores relevance, drafts replies, sets status `pending_review`
- `review_app.py` — Streamlit dashboard for review + the manual-post list
- `redraft_queue.py` — re-draft queued items after a prompt change

## Notes

- Start with a small, specific keyword list and 2-3 subreddits. Broaden
  once you've seen how the relevance scoring performs.
- Keep posting volume low and organic-looking — a handful of thoughtful
  replies a day beats dozens of generic ones, both for Reddit's spam
  filters and for actually building trust.
- The relevance/drafting prompts in `prompts.py` are a starting point —
  tune them with real examples from your target subreddits.
