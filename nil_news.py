# ======= BEGIN nil_news.py =======
#!/usr/bin/env python3
"""nil_news.py – Crawl NIL‑related news, optionally summarise with GPT, store in
SQLite, and expose JSON endpoints at /summaries and /latest."""
from __future__ import annotations

import argparse
import asyncio as _asyncio
import datetime as _dt
import hashlib as _hash
import os
from pathlib import Path
from typing import Any, Dict, List

import aiohttp
import aiosqlite
import feedparser
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from trafilatura import extract

# ── Optional GPT ---------------------------------------------------
try:
    import openai  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore

load_dotenv()

# ── Config ---------------------------------------------------------
_CFG_PATH = Path(__file__).with_name("config.yaml")
_DEFAULT_CFG: Dict[str, Any] = {
    "feeds": [
        "https://www.espn.com/college-sports/rss",
        "https://sports.yahoo.com/college/rss",
        "https://www.si.com/college/.rss",
        "https://feeds.feedburner.com/CollegeSportsNews",
        "https://rssfeeds.usatoday.com/UsatodaycomCollegeSports-TopStories",
        "https://feeds.latimes.com/latimes/sports/college",
        "https://frontofficesports.com/feed/",
        "https://www.sportsbusinessjournal.com/RSS/News.aspx",
        "https://sportico.com/feed/",
        "https://www.sportslawblog.com/atom.xml",
        "https://www.on3.com/nil/feed/",
        "https://www.on3.com/transfer-portal/feed/",
        "https://www.on3.com/high-school/feed/",
        "https://247sports.com/rss/",
        "https://www.ncaa.org/rss.xml",
        "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+high+school+athlete&hl=en-US&gl=US&ceid=US:en",
    ],
    "keywords": [
        "nil", "name image likeness", "collective", "booster",
        "endorsement", "sponsorship", "brand deal", "marketing",
        "royalty", "licensing", "revenue share", "donor",
        "deal", "contract", "agreement", "payout", "valuation",
        "athlete", "student-athlete", "recruit", "prospect",
        "high school", "coach", "ncaa",
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
CFG = _DEFAULT_CFG | yaml.safe_load(_CFG_PATH.read_text())

# ── Database -------------------------------------------------------
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

# ── Summaries ------------------------------------------------------
_PROMPT = CFG["openai"]["prompt_prefix"]

def _summarise(text: str) -> str:
    if openai is None or os.getenv("OPENAI_API_KEY") is None:
        return (text[:300].replace("\n", " ") + "…") if len(text) > 300 else text
    try:
        resp = openai.ChatCompletion.create(
            model=CFG["openai"].get("model", "gpt-3.5-turbo"),
            messages=[{"role": "user", "content": f"{_PROMPT}\n\n{text}"}],
            max_tokens=CFG["openai"].get("max_tokens", 128),
            temperature=CFG["openai"].get("temperature", 0.3),
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("[warn] OpenAI summarisation failed:", e)
        return (text[:300].replace("\n", " ") + "…") if len(text) > 300 else text

# ── Crawler --------------------------------------------------------
_USER_AGENT = "NILNewsBot/3.2 (+https://github.com/example/nil-news)"
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
        tasks: List[_asyncio.Task[Any]] = []
        for feed in CFG["feeds"]:
            parsed = feedparser.parse(feed)
            if parsed.bozo:
                print(f"[warn] bad feed: {feed}")
                continue
            tasks.extend(self._process_entry(e) for e in parsed.entries)
        if tasks:
            await _asyncio.gather(*tasks)

# ── Scheduler ------------------------------------------------------
async def continuous_crawl(interval_min: int):
    db = await init_db()
    crawler = NILCrawler(db)
    try:
        while True:
            start = _dt.datetime.utcnow()
            await crawler.crawl_once()
            elapsed = (_dt.datetime.utcnow() - start).total_seconds()
            await _asyncio.sleep(max(0, interval_min * 60 - elapsed))
    except _asyncio.CancelledError:
        pass
    finally:
        await db.close()

# ── FastAPI --------------------------------------------------------
app = FastAPI(title="NIL News API", version
# Health-check so Render sees 200 instead of 405
@app.head("/")
async def _ping() -> Response:
    return Response(status_code=200)

# Root
@app.get("/")
async def root():
    return {"message": "Welcome to NIL News API",
            "endpoints": ["/summaries", "/latest"]}

# Summaries (up to 5 000)
@app.get("/summaries")
async def summaries(limit: int = 50):
    if limit > 5000:
        raise HTTPException(400, "limit too high")
    sql = """
        SELECT title, url, published, brief FROM stories
        ORDER BY COALESCE(published, crawled_at) DESC LIMIT ?
    """
    async with app.state.db.execute(sql, (limit,)) as cur:
        rows = await cur.fetchall()
    return [dict(zip(("title", "url", "published", "brief"), r)) for r in rows]

# Latest
@app.get("/latest")
async def latest():
    sql = """
        SELECT title, url, published, brief FROM stories
        ORDER BY COALESCE(published, crawled_at) DESC LIMIT 1
    """
    async with app.state.db.execute(sql) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "no stories yet")
    return dict(zip(("title", "url", "published", "brief"), row))

# ── CLI entrypoint: crawler or API ────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NIL News (crawler + API)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    crawl_p = sub.add_parser("crawl", help="run continuous crawler")
    crawl_p.add_argument("--interval", type=int,
                         default=CFG["crawl_interval_min"],
                         help="minutes between crawl cycles")

    serve_p = sub.add_parser("serve", help="launch JSON API")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.cmd == "crawl":
        _asyncio.run(continuous_crawl(args.interval))
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
# ======= END nil_news.py =======
