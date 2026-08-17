# What this project does (read this first)

**Short version: this is a read-only research + drafting tool. It never posts
to Reddit, never logs in, and contains no write/automation code.**

It helps one person on a small team find public Reddit discussions about AI
agent memory / RAG / context management and draft genuinely helpful, on-topic
replies. A human reviews and edits every draft, then posts approved ones
**manually, as themselves**, through the normal reddit.com website.

## What it does

1. **Read** public submissions and comments from a small set of technical
   subreddits (currently via Reddit's public RSS feeds; the pending API
   request would replace RSS with read-only GET requests to the same public
   data).
2. **Filter** them against a keyword list (e.g. "agent memory", "RAG",
   "context window").
3. **Score & draft** — an LLM rates how relevant each post is and drafts a
   candidate reply.
4. **Human review** — a person reads the original post, edits the draft, and
   approves or rejects it in a local Streamlit dashboard.
5. **Post manually** — approved replies are copied and posted by a human
   through reddit.com. The tool itself never posts.

## What it explicitly does NOT do

- ❌ No posting, commenting, replying, voting, or moderating via the API
- ❌ No private messages / DMs
- ❌ No logging in as a bot; no automated actions of any kind
- ❌ No mass automation — a handful of human-reviewed replies per day at most
- ❌ No scraping of non-public or private data
- ❌ No redistribution of Reddit data

There is no posting code anywhere in this repository. The fetch path
(`fetch_scraper.py`) is read-only, and the only "output" is a local review
dashboard for a human.

## Data handling

Stores public post text, public author usernames, permalinks, and engagement
counts in a **local SQLite database** used only to power the internal review
queue and to avoid processing the same post twice. Nothing is shared,
published, or sold.

## File map

| File | Role |
|------|------|
| `fetch_scraper.py` | Read-only fetch of public posts (RSS) — **no writes** |
| `relevance_agent.py` | LLM scores relevance and drafts a reply |
| `prompts.py` | The scoring/drafting prompt templates |
| `review_app.py` | Streamlit dashboard: human review + manual-post list |
| `db.py` | Local SQLite store (the review queue / memory) |
| `config.py` | Loads settings from `.env` (LLM + targeting; **no Reddit creds**) |
| `redraft_queue.py` | Re-draft queued items after a prompt change |

## Why this needs API access (and not Devvit)

Devvit builds interactive apps that run *inside* Reddit's UI for a subreddit's
users. This is an external, off-platform tool that runs on my own machine,
feeds public post data into an external LLM and a local review dashboard, and
serves my team's internal drafting workflow — not an in-feed Reddit experience.
It only needs **read** access to public post data.
