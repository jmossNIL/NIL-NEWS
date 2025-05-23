# ======= BEGIN nil_news.py =======
#!/usr/bin/env python3
"""nil_news.py – Crawl NIL‑related news, summarize (via OpenAI if key is set),
store in SQLite, and expose /summaries & /latest JSON endpoints."""
from __future__ import annotations

import argparse
import asyncio as _asyncio
import datetime as _dt
import hashlib as _hash
import os
from pathlib import Path
from typing import Any, Dict

import aiohttp
import aiosqlite
import feedparser
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from trafilatura import extract

# Optional GPT summaries
try:
    import openai  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore

load_dotenv()

# ──────────────────────────── CONFIG ────────────────────────────
_CFG_PATH = Path(__file__).with_name("config.yaml")
_DEFAULT_CFG: dict[str, Any] = {
    "feeds": [
        # Mainstream
        "https://www.espn.com/college-sports/rss",
        "https://sports.yahoo.com/college/rss",
        "https://www.si.com/college/.rss",
        "https://feeds.feedburner.com/CollegeSportsNews",
        # National papers
        "https://rssfeeds.usatoday.com/UsatodaycomCollegeSports-TopStories",
        "https://feeds.latimes.com/latimes/sports/college",
        # Business / legal
        "https://frontofficesports.com/feed/",
        "https://www.sportsbusinessjournal.com/RSS/News.aspx",
        "https://sportico.com/feed/",
        "https://www.sportslawblog.com/atom.xml",
        # NIL‑focused / recruiting
        "https://www.on3.com/nil/feed/",
        "https://www.on3.com/transfer-portal/feed/",
        "https://www.on3.com/high-school/feed/",
        "https://247sports.com/rss/",
        # Governing bodies
        "https://www.ncaa.org/rss.xml",
        # Google News queries
        "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+high+school+athlete&hl=en-US&gl=US&ceid=US:en",
        # Twitter/X via RSSHub (may fail occasionally)
        "https://rsshub.app/twitter/user/On3NIL",
        "https://rsshub.app/twitter/user/SportsBizMiss",
        "https://rsshub.app/twitter/user/DarrenHeitner",
        "https://rsshub.app/twitter/user/BusinessOfCollegeSports",
        "https://rsshub.app/twitter/user/jeremydarlow",
    ],
    "keywords": [
        # Core NIL
        "nil", "name image likeness", "collective", "booster",
        "endorsement", "sponsorship", "brand deal", "marketing",
        "royalty", "licensing", "revenue share", "donor",
        # Money words
        "deal", "contract", "agreement", "payout", "valuation",
        "funding", "investment", "capital", "million", "billion",
        # Legal / policy
        "state law", "federal bill", "compliance", "guideline",
        "regulation", "antitrust", "lawsuit", "injunction", "settlement",
        # People
        "athlete", "student-athlete", "recruit", "prospect", "signee",
        "high school", "prep", "junior", "coach", "administrator",
        # Processes
        "transfer portal", "transfer window", "eligibility",
        # Orgs / conferences
        "ncaa", "sec", "big ten", "acc", "big 12", "pac-12",
        # Known collectives examples
        "gator collective", "one illinois nil", "texasonefund",
    ],
    "db_path": "nil_news.db",
    "crawl_interval_min": 5,
    "openai": {
        "model": "gpt-3.5-turbo",
        "max_tokens": 128,
        "temperature": 0.3,
        "prompt_prefix": (
            "Summarise the following college sports NIL news article in three "
            "sentences (~60 words). Focus on money figures, athletes, schools, "
            "and implications:"
        ),
    },
}

if not _CFG_PATH.exists():
    _CFG_PATH.write_text(yaml.safe_dump(_DEFAULT_CFG))
CFG: dict[str, Any] = _DEFAULT_CFG | yaml.safe_load(_CFG_PATH.read_text())

# ──────────────────────── DATABASE SETUP ─────────────────────────
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stories (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    url        TEXT,
    published  TEXT,
    summary    TEXT,
    brief      TEXT,
    crawled_at TEXT
);
"""

async def init_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(CFG["db_path"])
    await db.execute(_SCHEMA_SQL)
    async with db.execute("PRAGMA table_info(stories)") as cur:
        cols = [row[1] async for row in cur]
    if "brief" not in cols:
        await db.execute("ALTER TABLE stories ADD COLUMN brief TEXT")
        await db.commit()
    return db

# ────────────────────────── SUMMARIES ───────────────────────────
_PROMPT = CFG["openai"]["prompt_prefix"]

def _summarise(text: str) -> str:
    """Return GPT summary if key set; else fallback excerpt."""
    if openai is None or os.getenv("OPENAI_API_KEY") is None:
        return (text[:300].replace("\n", " ") + "…") if len(text) > 300 else text
    try:
        resp = openai.ChatCompletion.create(
            model=CFG["openai"]["model"],
            messages=[{"role": "user", "content": f"{_PROMPT}\n\n{text}"}],
            max_tokens=CFG["openai"].get("max_tokens", 128),
            temperature=CFG["openai"].get("temperature", 0.3),
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:  # pragma: no cover
        print("[warn] OpenAI summarisation failed:", e)
        return (text[:300].replace("\n", " ") + "…") if len(text) > 300 else text

# ────────────────────────── CRAWLER ─────────────────────────────
_USER_AGENT = "NILNewsBot/2.0 (+https://github.com/example/nil-news)"
_TIMEOUT = aiohttp.ClientTimeout(total=10)

class NILCrawler:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self.keywords = [k.lower() for k in CFG["keywords"]]

    def _is_relevant(self, txt: str) -> bool:
        return any(k in txt.lower() for k in self.keywords)

    async def _exists(self, story_id: str) -> bool:
        async with self.db.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)) as cur:
            return await cur.fetchone() is not None

    async def _fetch_html(self, url: str) -> str | None:
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT) as s:
                async with s.get(url) as r:
                    r.raise_for_status()
                    return await r.text()
        except Exception as e:
            print("[warn] fetch failure:", e)
            return None

    async def _process_entry(self, entry: Dict[str, Any]):
        url = entry.get("link")
        if not url:
            return
        story_id = _hash.sha256(url.encode()).hexdigest()
        if await self._exists(story_id):
            return
        html = await self._fetch_html(url)
        if not html:
            return
        text = extract(html, include_comments=False, include_tables=False) or html
        if not self._is_relevant(text):
            return
        brief = _summarise(text)
        await self.db.execute(
            "INSERT INTO stories VALUES (?,?,?,?,?,?,?)",
            (
                story_id,
                entry.get("title", "(no-title)"),
                url,
                entry.get("published", ""),
                text[:8000],
                brief,
                _dt.datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        await self.db.commit()
        print("[+] stored:", entry.get("title"))

    async def crawl_once(self):
        """Fetch all feeds once and process entries."""
        tasks: list[asyncio.Task] = []
        for feed in CFG["feeds"]:
            parsed = feedparser.parse(feed)
            if parsed.bozo:
                print(f"[warn] bad feed: {feed}")
                continue  # skip invalid feed
            tasks.extend(self._process
