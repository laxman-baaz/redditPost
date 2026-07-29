"""Scores relevance and drafts replies for items with status='new'.

For each new item:
  1. Ask the LLM whether/how to engage (relevance_score, should_mention_product).
  2. If relevance_score is below RELEVANCE_THRESHOLD -> mark 'skipped'.
  3. Otherwise draft a reply and mark 'pending_review' for a human to check
     in the Streamlit dashboard (review_app.py).

Run as a long-lived process:
    python relevance_agent.py
"""
import json
import re
import time

from langchain_core.messages import SystemMessage, HumanMessage

from config import settings
from db import init_db, get_items_by_status, update_item
import prompts

RELEVANCE_THRESHOLD = 5  # 0-10 scale; tune based on real results


def build_llm():
    """Construct the chat model for the configured LLM_PROVIDER.

    - "gemini"  -> ChatOpenAI against Gemini's OpenAI-compatible endpoint (API key)
    - "bedrock" -> ChatBedrockConverse against AWS Bedrock (AWS CLI / boto3 creds)
    """
    provider = settings.LLM_PROVIDER
    if provider == "bedrock":
        from langchain_aws import ChatBedrockConverse

        # Note: newer Claude models (Sonnet 5, Opus 4.7+) reject `temperature`,
        # so it is intentionally omitted here.
        return ChatBedrockConverse(
            model=settings.BEDROCK_MODEL_ID,
            region_name=settings.AWS_REGION,
            max_tokens=1024,
        )
    if provider == "gemini":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            max_tokens=1024,
            temperature=0.3,
        )
    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Use 'gemini' or 'bedrock'."
    )


llm = build_llm()


def _text_of(response) -> str:
    """Extract plain text from a chat response.

    Most providers return a string. Some (e.g. Bedrock Claude with reasoning)
    return a list of content blocks; we keep only the text blocks.
    """
    content = response.content
    if isinstance(content, str):
        return content.strip()
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def score_relevance(item: dict) -> dict:
    system = prompts.RELEVANCE_SYSTEM_PROMPT.format(
        product_name=settings.PRODUCT_NAME,
        product_url=settings.PRODUCT_URL,
        product_description=settings.PRODUCT_DESCRIPTION,
    )
    user = prompts.RELEVANCE_USER_PROMPT.format(
        subreddit=item["subreddit"], body=item["body"][:4000]
    )
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    text = _text_of(response)
    # Strip accidental markdown fences if the model adds them
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


_PREAMBLE_RE = re.compile(
    r"^\s*(here'?s?\s+(a|my|the)\s+(draft|reply|response)[^\n:]*:|draft\s*(reply)?\s*:)\s*",
    re.IGNORECASE,
)
# A trailing meta-note the model sometimes appends, e.g. "[note: this works because ...]".
_META_NOTE_RE = re.compile(r"\n*\s*\[?\s*note:.*$", re.IGNORECASE | re.DOTALL)


def _clean_draft(text: str) -> str:
    """Strip preambles / meta-notes the model sometimes wraps around the reply."""
    text = _PREAMBLE_RE.sub("", text)
    text = _META_NOTE_RE.sub("", text)
    return text.strip()


def draft_reply(item: dict, should_mention_product: bool) -> str:
    system = prompts.DRAFT_SYSTEM_PROMPT.format(
        product_name=settings.PRODUCT_NAME,
        product_url=settings.PRODUCT_URL,
        product_description=settings.PRODUCT_DESCRIPTION,
    )
    user = prompts.DRAFT_USER_PROMPT.format(
        subreddit=item["subreddit"],
        body=item["body"][:4000],
        should_mention_product=should_mention_product,
    )
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return _clean_draft(_text_of(response))


def process_item(item: dict):
    reddit_id = item["reddit_id"]
    try:
        result = score_relevance(item)
    except Exception as e:
        print(f"[relevance_agent] scoring failed for {reddit_id}: {e}")
        return

    score = result.get("relevance_score", 0)
    should_mention = bool(result.get("should_mention_product", False))

    update_item(
        reddit_id,
        relevance_score=score,
        relevance_reasoning=result.get("reasoning", ""),
        should_mention_product=int(should_mention),
        scored_at=int(time.time()),
    )

    # Replies to our own comments are always worth a human look, regardless
    # of topical relevance score, since someone engaged with us directly.
    is_reply_to_us = bool(item.get("is_reply_to_us"))

    if score < RELEVANCE_THRESHOLD and not is_reply_to_us:
        update_item(reddit_id, status="skipped")
        print(f"Skipped {reddit_id} (score={score})")
        return

    try:
        draft = draft_reply(item, should_mention)
    except Exception as e:
        print(f"[relevance_agent] drafting failed for {reddit_id}: {e}")
        return

    update_item(reddit_id, draft_reply=draft, status="pending_review")
    print(f"Drafted reply for {reddit_id} (score={score}) -> pending_review")


def main():
    init_db()
    while True:
        items = get_items_by_status("new", limit=20)
        for item in items:
            process_item(item)
        time.sleep(settings.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
