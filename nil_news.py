#!/usr/bin/env python3
"""
nil_news.py — crawl NIL-related news, optionally summarise with GPT,
store in SQLite, and expose JSON endpoints (/summaries, /latest).
"""
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

# ── GPT (optional) -------------------------------------------------
try:
    import openai  # type: ignore
except ModuleNotFoundError:
    openai = None  # type: ignore

load_dotenv()

# ── Config ---------------------------------------------------------
_CFG_PATH = Path(__file__).with_name("config.yaml")
_DEFAULT_CFG: Dict[str, Any] = {
    "feeds": [
        # Major Sports & NIL-specific outlets
        "https://www.nil-wire.com/feed/",
        "https://www.on3.com/nil/feed/",
        "https://www.on3.com/transfer-portal/feed/",
        "https://www.on3.com/high-school/feed/",
        "https://frontofficesports.com/feed/",
        "https://www.sportsbusinessjournal.com/RSS/News.aspx",
        "https://sportico.com/feed/",
        "https://businessofcollegesports.com/feed/",
        
        # Sports Law & Business feeds
        "https://www.sportslawblog.com/atom.xml",
        "https://blogs.duanemorris.com/sportslaw/feed/",
        "https://www.gmlaw.com/feed/",
        "https://www.lawinsport.com/rss/news",
        "https://legalsportsreport.com/feed/",
        "https://combatsportslaw.com/feed/",
        "https://sportslawinsider.com/feed/",
        
        # College Sports & Recruiting
        "https://247sports.com/rss/",
        "https://www.espn.com/college-sports/rss",
        "https://sports.yahoo.com/college/rss",
        "https://www.si.com/college/.rss",
        "https://feeds.feedburner.com/CollegeSportsNews",
        "https://rssfeeds.usatoday.com/UsatodaycomCollegeSports-TopStories",
        "https://feeds.latimes.com/latimes/sports/college",
        "https://www.ncaa.org/rss.xml",
        "https://accsports.com/feed/",
        "https://collegeathleteinsight.com/feed/",
        "https://nlusports.com/blog/feed/",
        "https://therecruitingcode.com/blog/feed/",
        
        # Business & Financial feeds
        "https://www.reuters.com/business/sports/rss",
        "https://www.cnbc.com/id/10000831/device/rss/rss.html",  # Sports Business
        "https://feeds.bloomberg.com/blaw/news.rss",
        "https://feeds.fortune.com/fortune/sports",
        
        # Google News searches for real-time NIL coverage
        "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+high+school+athlete&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+collective+booster&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+marketplace+endorsement&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=college+sports+transfer+portal&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NCAA+antitrust+lawsuit&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=\"House+v+NCAA\"+settlement&hl=en-US&gl=US&ceid=US:en",
        
        # Team-specific feeds with strong NIL coverage
        "https://on3.com/teams/texas-longhorns/feed/",
        "https://on3.com/teams/texas-am-aggies/feed/",
        "https://on3.com/teams/miami-hurricanes/feed/",
        "https://on3.com/teams/oregon-ducks/feed/",
        "https://on3.com/teams/lsu-tigers/feed/",
        "https://on3.com/teams/georgia-bulldogs/feed/",
        "https://on3.com/teams/alabama-crimson-tide/feed/",
        
        # Conferences with major NIL activity
        "https://www.saturdaydownsouth.com/sec/feed/",
        "https://www.bigten.org/rss.aspx",
        "https://www.pac-12.com/rss.xml",
        
        # Social Media & Influencer Marketing (NIL-adjacent)
        "https://www.socialmediatoday.com/rss.xml",
        "https://marketingland.com/feed",
        "https://www.adweek.com/feed/",
        
        # Additional specialized sources
        "https://www.athleticbusiness.com/feed/",
        "https://www.streetandsmith.com/feed/",
    ],
    "keywords": [
        # Core NIL terms
        "nil", "name image likeness", "name, image, likeness", "nil deal", "nil contract",
        "nil marketplace", "nil collective", "nil platform", "nil valuation", "nil money",
        "nil endorsement", "nil agreement", "nil opportunity", "nil rights", "nil policy",
        
        # Business & Legal terms
        "collective", "booster", "endorsement", "sponsorship", "brand deal", "marketing deal",
        "licensing", "revenue share", "royalty", "compensation", "payout", "valuation",
        "contract", "agreement", "settlement", "lawsuit", "antitrust", "transfer portal",
        
        # Key legal cases & entities
        "house v ncaa", "house settlement", "opendorse", "marketpryce", "icon source",
        "clean konnect", "mogl", "nil store", "athlete direct", "gator collective",
        "the fund", "spyre sports", "rising spear", "swarm collective",
        
        # Social media & influencer terms
        "social media influencer", "athlete influencer", "nil influencer", "instagram deal",
        "tiktok partnership", "youtube sponsorship", "content creator", "brand ambassador",
        "social media marketing", "digital marketing", "personal brand",
        
        # Sports & athlete terms
        "student-athlete", "college athlete", "high school athlete", "recruit", "prospect",
        "transfer portal", "recruiting", "scholarship", "ncaa", "naia", "division i",
        "power 5", "power 4", "sec", "big ten", "acc", "big 12", "pac-12",
        
        # Business terms
        "athletic department", "compliance", "eligibility", "fair market value",
        "pay for play", "recruiting inducement", "booster payment", "donor",
        "venture capital", "investment", "startup", "technology platform",
        
        # Financial terms
        "million dollar deal", "six figure deal", "earnings", "profit", "revenue",
        "monetize", "monetization", "financial literacy", "tax implications",
        "business entity", "llc formation", "brand management",
        
        # High-profile athletes (for catching major stories)
        "shedeur sanders", "olivia dunne", "livvy dunne", "cavinder twins",
        "quinn ewers", "anthony hamilton", "bronny james", "shareef o'neal",
        
        # Trending topics
        "house settlement", "nil clearinghouse", "third party nil", "booster restrictions",
        "revenue sharing", "athlete employment", "title ix", "gender equity",
        "international athletes", "f-1 visa", "high school nil",
        
        # Technology & platforms
        "nil app", "athlete marketplace", "deal disclosure", "compliance software",
        "nil analytics", "social media analytics", "engagement rate", "follower count",
    ],
    "db_path": "nil_news.db",
    "crawl_interval_min": 3,  # More frequent crawling for breaking news
    "openai": {
        "model": "gpt-4o-mini",  # Updated model
        "max_tokens": 150,  # Slightly longer summaries
        "temperature": 0.2,  # More focused summaries
        "prompt_prefix": (
            "Summarize this NIL/college sports news article in 2-3 sentences (~75 words). "
            "Focus on: key figures/amounts, athletes/schools involved, business implications, "
            "and legal/regulatory impact. Be specific about numbers and names:"
        ),
    },
}

# write default config if missing
if not _CFG_PATH.exists():
    _CFG_PATH.write_text(yaml.safe_dump(_DEFAULT_CFG))

# merge user overrides safely
CFG: Dict[str, Any] = {**_DEFAULT_CFG, **(yaml.safe_load(_CFG_PATH.read_text()) or {})}

# ── Database -------------------------------------------------------
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stories (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    url        TEXT,
    published  TEXT,
    summary    TEXT,
    brief      TEXT,
    crawled_at TEXT,
    source     TEXT,
    category   TEXT
);
"""

async def init_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(CFG["db_path"])
    await db.execute(_SCHEMA_SQL)
    
    # Check and add new columns if they don't exist
    async with db.execute("PRAGMA table_info(stories)") as cur:
        cols = [row[1] async for row in cur]
    
    if "brief" not in cols:
        await db.execute("ALTER TABLE stories ADD COLUMN brief TEXT")
    if "source" not in cols:
        await db.execute("ALTER TABLE stories ADD COLUMN source TEXT")
    if "category" not in cols:
        await db.execute("ALTER TABLE stories ADD COLUMN category TEXT")
    
    await db.commit()
    return db

# ── Summaries ------------------------------------------------------
_PROMPT = CFG["openai"]["prompt_prefix"]

def _summarise(text: str) -> str:
    """Return GPT summary if key set; otherwise fallback to excerpt."""
    if openai is None or os.getenv("OPENAI_API_KEY") is None:
        return (text[:350].replace("\n", " ") + "…") if len(text) > 350 else text
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
        return (text[:350].replace("\n", " ") + "…") if len(text) > 350 else text

# ── Crawler --------------------------------------------------------
_USER_AGENT = "NILNewsBot/4.0 (+https://github.com/example/nil-news)"
_TIMEOUT = aiohttp.ClientTimeout(total=15)

class NILCrawler:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self.keywords = [k.lower() for k in CFG["keywords"]]

    def _is_relevant(self, txt: str) -> bool:
        """Enhanced relevance checking with weighted keywords."""
        txt_lower = txt.lower()
        
        # High-priority keywords that alone make an article relevant
        high_priority = ["nil deal", "nil collective", "nil marketplace", "house v ncaa", 
                        "nil endorsement", "athlete endorsement", "nil money", "nil contract"]
        
        # Check for high-priority keywords first
        for keyword in high_priority:
            if keyword in txt_lower:
                return True
        
        # For other keywords, require at least 2 matches for relevance
        matches = sum(1 for k in self.keywords if k in txt_lower)
        return matches >= 2

    def _categorize_content(self, title: str, text: str) -> str:
        """Categorize the content based on keywords."""
        combined = (title + " " + text).lower()
        
        if any(word in combined for word in ["lawsuit", "settlement", "antitrust", "legal", "court"]):
            return "Legal"
        elif any(word in combined for word in ["collective", "booster", "donor", "fund"]):
            return "Collectives"
        elif any(word in combined for word in ["marketplace", "platform", "app", "technology"]):
            return "Technology"
        elif any(word in combined for word in ["social media", "influencer", "instagram", "tiktok"]):
            return "Social Media"
        elif any(word in combined for word in ["transfer portal", "recruiting", "prospect"]):
            return "Recruiting"
        elif any(word in combined for word in ["high school", "prep", "youth"]):
            return "High School"
        else:
            return "General"

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
            print(f"[warn] fetch failure for {url}: {e}")
            return None

    def _extract_source(self, url: str) -> str:
        """Extract source name from URL."""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            
            # Map common domains to friendly names
            source_map = {
                "nil-wire.com": "NIL Wire",
                "on3.com": "On3",
                "247sports.com": "247Sports",
                "frontofficesports.com": "Front Office Sports",
                "businessofcollegesports.com": "Business of College Sports",
                "sportsbusinessjournal.com": "Sports Business Journal",
                "espn.com": "ESPN",
                "si.com": "Sports Illustrated",
                "yahoo.com": "Yahoo Sports",
                "ncaa.org": "NCAA",
                "duanemorris.com": "Duane Morris Sports Law",
                "reuters.com": "Reuters",
                "bloomberg.com": "Bloomberg Law",
            }
            
            for key, value in source_map.items():
                if key in domain:
                    return value
            
            # Default to cleaned domain name
            return domain.replace("www.", "").replace(".com", "").title()
        except:
            return "Unknown"

    async def _process_entry(self, entry: Dict[str, Any], feed_url: str):
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
        title = entry.get("title", "(no-title)")
        
        if not self._is_relevant(title + " " + text):
            return
            
        brief = _summarise(text)
        source = self._extract_source(url)
        category = self._categorize_content(title, text)
        
        await self.db.execute(
            "INSERT INTO stories VALUES (?,?,?,?,?,?,?,?,?)",
            (
                story_id,
                title,
                url,
                entry.get("published", ""),
                text[:8000],  # Truncate long articles
                brief,
                _dt.datetime.utcnow().isoformat(timespec="seconds"),
                source,
                category,
            ),
        )
        await self.db.commit()
        print(f"[+] stored: {title} [{source}] [{category}]")

    async def crawl_once(self):
        tasks: List[_asyncio.Task[Any]] = []
        
        for feed_url in CFG["feeds"]:
            try:
                parsed = feedparser.parse(feed_url)
                if parsed.bozo:
                    print(f"[warn] bad feed: {feed_url}")
                    continue
                    
                for entry in parsed.entries[:10]:  # Limit to 10 most recent per feed
                    task = _asyncio.create_task(self._process_entry(entry, feed_url))
                    tasks.append(task)
                    
            except Exception as e:
                print(f"[error] processing feed {feed_url}: {e}")
                
        if tasks:
            await _asyncio.gather(*tasks, return_exceptions=True)

# ── Scheduler ------------------------------------------------------
async def continuous_crawl(interval_min: int):
    db = await init_db()
    crawler = NILCrawler(db)
    try:
        while True:
            start = _dt.datetime.utcnow()
            print(f"[info] Starting crawl at {start}")
            await crawler.crawl_once()
            elapsed = (_dt.datetime.utcnow() - start).total_seconds()
            print(f"[info] Crawl completed in {elapsed:.2f}s")
            await _asyncio.sleep(max(0, interval_min * 60 - elapsed))
    except _asyncio.CancelledError:
        pass
    finally:
        await db.close()

# ── FastAPI app ----------------------------------------------------
app = FastAPI(title="NIL News API", version="2.0.0", description="Enhanced NIL news aggregator")

@app.on_event("startup")
async def _startup():
    app.state.db = await init_db()
    app.state.crawl_task = _asyncio.create_task(
        continuous_crawl(CFG["crawl_interval_min"])
    )

@app.on_event("shutdown")
async def _shutdown():
    app.state.crawl_task.cancel()
    await app.state.db.close()

# Health-check
@app.head("/")
async def _ping() -> Response:
    return Response(status_code=200)

# Root
@app.get("/")
async def root():
    return {
        "message": "Welcome to Enhanced NIL News API",
        "version": "2.0.0",
        "endpoints": ["/summaries", "/latest", "/categories", "/sources", "/stats"]
    }

# ── Enhanced endpoints ─────────────────────────────────────────────
@app.get("/summaries")
async def summaries(limit: int = 50, category: str = None, source: str = None):
    if limit > 5000:
        raise HTTPException(400, "limit too high")
    
    where_clauses = []
    params = []
    
    if category:
        where_clauses.append("category = ?")
        params.append(category)
    
    if source:
        where_clauses.append("source = ?")
        params.append(source)
    
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    
    sql = f"""
        SELECT title, url, published, brief, source, category, crawled_at
        FROM stories
        {where_sql}
        ORDER BY COALESCE(published, crawled_at) DESC
        LIMIT ?
    """
    params.append(limit)
    
    async with app.state.db.execute(sql, params) as cur:
        rows = await cur.fetchall()
    
    return [dict(zip(("title", "url", "published", "brief", "source", "category", "crawled_at"), r)) for r in rows]

@app.get("/latest")
async def latest():
    sql = """
        SELECT title, url, published, brief, source, category, crawled_at
        FROM stories
        ORDER BY COALESCE(published, crawled_at) DESC
        LIMIT 1
    """
    async with app.state.db.execute(sql) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "no stories yet")
    return dict(zip(("title", "url", "published", "brief", "source", "category", "crawled_at"), row))

@app.get("/categories")
async def categories():
    """Get available categories with counts."""
    sql = """
        SELECT category, COUNT(*) as count
        FROM stories
        WHERE category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
    """
    async with app.state.db.execute(sql) as cur:
        rows = await cur.fetchall()
    return [{"category": r[0], "count": r[1]} for r in rows]

@app.get("/sources")
async def sources():
    """Get available sources with counts."""
    sql = """
        SELECT source, COUNT(*) as count
        FROM stories
        WHERE source IS NOT NULL
        GROUP BY source
        ORDER BY count DESC
    """
    async with app.state.db.execute(sql) as cur:
        rows = await cur.fetchall()
    return [{"source": r[0], "count": r[1]} for r in rows]

@app.get("/stats")
async def stats():
    """Get database statistics."""
    sql_total = "SELECT COUNT(*) FROM stories"
    sql_today = """
        SELECT COUNT(*) FROM stories 
        WHERE date(crawled_at) = date('now')
    """
    sql_week = """
        SELECT COUNT(*) FROM stories 
        WHERE crawled_at >= datetime('now', '-7 days')
    """
    
    async with app.state.db.execute(sql_total) as cur:
        total = (await cur.fetchone())[0]
    
    async with app.state.db.execute(sql_today) as cur:
        today = (await cur.fetchone())[0]
    
    async with app.state.db.execute(sql_week) as cur:
        week = (await cur.fetchone())[0]
    
    return {
        "total_stories": total,
        "stories_today": today,
        "stories_this_week": week,
        "active_feeds": len(CFG["feeds"]),
        "keywords_tracked": len(CFG["keywords"])
    }

# ── CLI entrypoint ────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enhanced NIL News (crawler + API)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    crawl_p = sub.add_parser("crawl", help="run continuous crawler")
    crawl_p.add_argument(
        "--interval", type=int,
        default=CFG["crawl_interval_min"],
        help="minutes between crawl cycles",
    )

    serve_p = sub.add_parser("serve", help="launch JSON API")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.cmd == "crawl":
        _asyncio.run(continuous_crawl(args.interval))
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
