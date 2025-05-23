# ======= BEGIN nil_news.py =======
#!/usr/bin/env python3
"""nil_news.py – crawl NIL news, build optional GPT summaries, store data
in SQLite, and expose a FastAPI JSON API at /summaries and /latest."""
from __future__ import annotations

# — standard libs —
import argparse
import asyncio as _asyncio
import datetime as _dt
import hashlib as _hash
import os
from pathlib import Path
from typing import Any, Dict

# — third‑party —
import aiohttp
import aiosqlite
import feedparser
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from trafilatura import extract

try:
    import openai  # optional GPT summaries
except ModuleNotFoundError:
    openai = None  # type: ignore

load_dotenv()

# ── Config ───────────────────────────────────────────────
_CFG_PATH = Path(__file__).with_name("config.yaml")
_DEFAULT_CFG = {
    "feeds": [
        "https://www.espn.com/college-sports/rss",
        "https://frontofficesports.com/feed/",
        "https://www.sportsbusinessjournal.com/RSS/News.aspx",
        "https://www.ncaa.org/rss.xml",
        "https://www.on3.com/nil/feed/",
    ],
    "keywords": [
        "nil", "name image likeness", "collective", "booster",
        "endorsement", "sponsorship", "transfer portal", "licensing",
        "lawsuit", "royalty", "deal", "contract", "pay",
    ],
    "db_path": "nil_news.db",
    "crawl_interval_min": 5,
    "openai": {
        "model": "gpt-3.5-turbo",
        "max_tokens": 128,
        "temperature": 0.3,
        "prompt_prefix": (
            "Summarise the following college sports NIL news article in "
            "three sentences (~60 words). Focus on money figures, athletes, "
            "schools, and implications:"
        ),
    },
}
if not _CFG_PATH.exists():
    _CFG_PATH.write_text(yaml.safe_dump(_DEFAULT_CFG))
CFG = _DEFAULT_CFG | yaml.safe_load(_CFG_PATH.read_text())

# ── Database ─────────────────────────────────────────────
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
    cols = [row[1] async for row in db.execute("PRAGMA table_info(stories)")]
    if "brief" not in cols:
        await db.execute("ALTER TABLE stories ADD COLUMN brief TEXT")
        await db.commit()
    return db

# ── Summaries ────────────────────────────────────────────
_PROMPT = CFG["openai"]["prompt_prefix"]

def _summarise(text: str) -> str:
    """Return ~60‑word summary using GPT if key present, else excerpt."""
    if openai is None or os.getenv("OPENAI_API_KEY") is None:
        return (text[:300].replace("\n", " ") + "…") if len(text) > 300 else text
    try:
        resp = openai.ChatCompletion.create(
            model=CFG["openai"]["model"],
            messages=[{"role": "user", "content": f"{_PROMPT}\n\n{text}"}],
            max_tokens=CFG["openai"]["max_tokens"],
            temperature=CFG["openai"]["temperature"],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("[warn] OpenAI summarisation failed:", e)
        return (text[:300].replace("\n", " ") + "…") if len(text) > 300 else text

# ── Crawler ──────────────────────────────────────────────
_USER_AGENT = "NILNewsBot/1.0 (+https://github.com/example/nil-news)"
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
        tasks = []
        for feed in CFG["feeds"]:
            parsed = feedparser.parse(feed)
            if parsed.bozo:
                print("[warn] bad feed:", feed)
                continue
            tasks.extend(self._process_entry(e) for e in parsed.entries)
        if tasks:
            await _asyncio.gather(*tasks)

# ── Scheduler ────────────────────────────────────────────
async def continuous_crawl(interval_min: int):
    db = await init_db()
    crawler = NILCrawler(db)
    try:
        while True:
            start = _dt.datetime.utcnow()
            await crawler.crawl_once()
            elapsed = (_dt.datetime.utcnow() - start).total_seconds()
            await _asyncio.sleep(max(0, interval_min * 60 - elapsed))
    except KeyboardInterrupt:
        print("[info] crawler stopped")
    finally:
        await db.close()

# ── FastAPI app ──────────────────────────────────────────
app = FastAPI(title="NIL News API", version="1.0.0")

@app.on_event("startup")
async def _startup():
    app.state.db = await init_db()

@app.on_event("shutdown")
async def _shutdown():
    await app.state.db.close()

@app.get("/summaries")
async def summaries(limit: int = 50):
    if limit > 500:
        raise HTTPException(400, "limit too high")
    async with app.state.db.execute(
        "SELECT title, url, published, brief FROM stories ORDER BY crawled_at DESC LIMIT ?",
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(zip(("title", "url", "published", "brief"), r)) for r in rows]

@app.get("/latest")
async def latest():
    async with app.state.db.execute(
        "SELECT title, url, published, brief FROM stories ORDER BY crawled_at DESC LIMIT 1"
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "no stories yet")
    return dict(zip(("title", "url", "published", "brief"), row))

# ── CLI entrypoint ───────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="NIL News (crawler + API)")
    sub = p.add_subparsers(dest="cmd", required=True)

    crawl_p = sub.add_parser("crawl", help="run continuous crawler")
    crawl_p.add_argument(
        "--interval", type=int, default
