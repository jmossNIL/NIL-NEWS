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
        # Major Sports & NIL-specific outlets (VERIFIED WORKING)
        "https://frontofficesports.com/feed/",
        "https://sportico.com/feed/",
        "https://businessofcollegesports.com/feed/",
        
        # Sports Law & Business feeds (VERIFIED WORKING)
        "https://www.sportslawblog.com/atom.xml",
        
        # College Sports & Recruiting (VERIFIED WORKING)
        "https://www.espn.com/college-sports/rss",
        "https://sports.yahoo.com/college/rss",
        "https://www.si.com/college/.rss",
        "https://feeds.feedburner.com/CollegeSportsNews",
        "https://rssfeeds.usatoday.com/UsatodaycomCollegeSports-TopStories",
        "https://feeds.latimes.com/latimes/sports/college",
        
        # Business & Financial feeds (VERIFIED WORKING)
        "https://www.cnbc.com/id/10000831/device/rss/rss.html",  # Sports Business
        "https://www.adweek.com/feed/",
        "https://marketingland.com/feed",
        
        # Google News searches for real-time NIL coverage (ALWAYS WORKING)
        "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+high+school+athlete&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+collective+booster&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+marketplace+endorsement&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=college+sports+transfer+portal&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NCAA+antitrust+lawsuit&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=\"House+v+NCAA\"+settlement&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=student+athlete+endorsement&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=college+sports+business&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=athletic+department+revenue&hl=en-US&gl=US&ceid=US:en",
        
        # 247Sports team feeds (Try WordPress format)
        "https://247sports.com/feed/",
        
        # On3 - Try different feed formats
        "https://www.on3.com/feed/",
        "https://www.on3.com/rss/",
        
        # Additional working sports feeds
        "https://www.ncaa.org/news/rss.xml",
        "https://www.athleticbusiness.com/rss.xml",
        
        # Team-specific working feeds (SB Nation sites use WordPress)
        "https://www.saturdayblitz.com/feed/",
        "https://www.burntorangenation.com/feed/",  # Texas Longhorns
        "https://www.goodbullhunting.com/feed/",    # Texas A&M
        "https://www.addictedtoquack.com/feed/",   # Oregon Ducks
        "https://www.andthevalleyshook.com/feed/", # LSU Tigers
        "https://www.dawgsports.com/feed/",        # Georgia Bulldogs
        "https://www.rollbamaroll.com/feed/",      # Alabama
        "https://www.stateoftheu.com/feed/",       # Miami Hurricanes
        
        # Conference news feeds
        "https://www.saturdaydownsouth.com/feed/",
        
        # Social Media & Tech (NIL-adjacent)
        "https://www.socialmediatoday.com/feed/",
        "https://techcrunch.com/tag/sports/feed/",
        
        # Additional NIL-relevant feeds
        "https://www.insidehighered.com/rss/news.xml",
        "https://www.theatlantic.com/feed/channel/technology/",
        "https://feeds.feedburner.com/TheAtlantic",
        
        # Academic and policy feeds
        "https://feeds.chronicle.com/chronicle/topstories",
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
    """Return GPT summary if key set; otherwise fallback to intelligent excerpt."""
    if openai is None or os.getenv("OPENAI_API_KEY") is None:
        # Intelligent fallback - extract first few sentences
        sentences = text.replace('\n', ' ').split('. ')
        # Filter out very short sentences and take first 2-3 good ones
        good_sentences = [s.strip() + '.' for s in sentences[:5] if len(s.strip()) > 20]
        summary = ' '.join(good_sentences[:2])
        return summary[:400] + "..." if len(summary) > 400 else summary
    
    try:
        # Enhanced prompt for better summaries
        enhanced_prompt = (
            "Provide a clear, informative 2-3 sentence summary (60-80 words) of this NIL/college sports article. "
            "Focus on: WHO (athletes/coaches/schools), WHAT (the deal/event/announcement), "
            "HOW MUCH (money/valuation if mentioned), and WHY it matters. "
            "Be specific about names, amounts, and implications:"
        )
        
        resp = openai.ChatCompletion.create(
            model=CFG["openai"]["model"],
            messages=[{"role": "user", "content": f"{enhanced_prompt}\n\n{text[:2000]}"}],  # More context
            max_tokens=100,  # Slightly longer for better summaries
            temperature=CFG["openai"]["temperature"],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("[warn] OpenAI summarisation failed:", e)
        # Better fallback
        sentences = text.replace('\n', ' ').split('. ')
        good_sentences = [s.strip() + '.' for s in sentences[:5] if len(s.strip()) > 20]
        summary = ' '.join(good_sentences[:2])
        return summary[:400] + "..." if len(summary) > 400 else summary

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

    def _normalize_date(self, date_str: str) -> str:
        """Normalize various date formats to ISO format for consistent sorting."""
        if not date_str:
            return _dt.datetime.utcnow().isoformat(timespec="seconds")
        
        try:
            # Try parsing with feedparser's time module first
            import time
            import email.utils
            
            # Handle RSS/Atom date formats
            if hasattr(feedparser, 'parse_date'):
                parsed = feedparser.parse_date(date_str)
                if parsed:
                    return _dt.datetime(*parsed[:6]).isoformat(timespec="seconds")
            
            # Try email.utils.parsedate_to_datetime for RFC 2822 dates
            try:
                parsed_dt = email.utils.parsedate_to_datetime(date_str)
                return parsed_dt.isoformat(timespec="seconds")
            except:
                pass
            
            # Fallback: try common formats
            common_formats = [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%a, %d %b %Y %H:%M:%S %z",
            ]
            
            for fmt in common_formats:
                try:
                    parsed = _dt.datetime.strptime(date_str.strip(), fmt)
                    return parsed.isoformat(timespec="seconds")
                except:
                    continue
                    
        except Exception as e:
            print(f"[warn] date parsing failed for '{date_str}': {e}")
        
        # If all parsing fails, use current time
        return _dt.datetime.utcnow().isoformat(timespec="seconds")

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
        
        # Get and normalize published date
        published_raw = entry.get("published") or entry.get("pubDate") or entry.get("updated") or ""
        published_normalized = self._normalize_date(published_raw)
        
        await self.db.execute(
            "INSERT INTO stories VALUES (?,?,?,?,?,?,?,?,?)",
            (
                story_id,
                title,
                url,
                published_normalized,  # Use normalized date
                text[:8000],  # Truncate long articles
                brief,
                _dt.datetime.utcnow().isoformat(timespec="seconds"),
                source,
                category,
            ),
        )
        await self.db.commit()
        print(f"[+] stored: {title} [{source}] [{category}] [{published_normalized[:10]}]")

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

# Add static file serving for CSS/JS if needed
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import Request
import json

# Templates for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIL News Dashboard</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/tailwindcss/2.2.19/tailwind.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .card-hover:hover { transform: translateY(-2px); box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
        .category-badge { background: linear-gradient(45deg, #ff6b6b, #ee5a24); }
        .source-badge { background: linear-gradient(45deg, #4ecdc4, #44a08d); }
        .fade-in { animation: fadeIn 0.5s ease-in; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .glass { background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.2); }
    </style>
</head>
<body class="bg-gray-50 font-sans">
    <!-- Header -->
    <header class="gradient-bg text-white shadow-lg">
        <div class="container mx-auto px-6 py-8">
            <div class="flex items-center justify-between">
                <div>
                    <h1 class="text-4xl font-bold mb-2">
                        <i class="fas fa-chart-line mr-3"></i>NIL News Dashboard
                    </h1>
                    <p class="text-blue-100 text-lg">Real-time Name, Image & Likeness news aggregation</p>
                </div>
                <div class="glass rounded-lg p-4">
                    <div class="text-right">
                        <div class="text-2xl font-bold" id="story-count">{{ total_stories }}</div>
                        <div class="text-sm opacity-75">Total Stories</div>
                    </div>
                </div>
            </div>
        </div>
    </header>

    <!-- Stats Bar -->
    <div class="bg-white border-b border-gray-200 py-4">
        <div class="container mx-auto px-6">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="text-center">
                    <div class="text-2xl font-bold text-blue-600" id="today-count">{{ stories_today }}</div>
                    <div class="text-sm text-gray-500">Stories Today</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-green-600" id="week-count">{{ stories_week }}</div>
                    <div class="text-sm text-gray-500">This Week</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-purple-600">{{ active_feeds }}</div>
                    <div class="text-sm text-gray-500">Active Feeds</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-red-600">{{ keywords_tracked }}</div>
                    <div class="text-sm text-gray-500">Keywords Tracked</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Filters -->
    <div class="container mx-auto px-6 py-6">
        <div class="bg-white rounded-lg shadow-md p-6 mb-6">
            <div class="flex flex-wrap gap-4 items-center">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Category</label>
                    <select id="category-filter" class="border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500">
                        <option value="">All Categories</option>
                        {% for cat in categories %}
                        <option value="{{ cat.category }}">{{ cat.category }} ({{ cat.count }})</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Source</label>
                    <select id="source-filter" class="border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500">
                        <option value="">All Sources</option>
                        {% for source in sources %}
                        <option value="{{ source.source }}">{{ source.source }} ({{ source.count }})</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Limit</label>
                    <select id="limit-filter" class="border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500">
                        <option value="25">25 stories</option>
                        <option value="50" selected>50 stories</option>
                        <option value="100">100 stories</option>
                        <option value="200">200 stories</option>
                    </select>
                </div>
                <div class="flex-1"></div>
                <button id="refresh-btn" class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors">
                    <i class="fas fa-refresh mr-2"></i>Refresh
                </button>
            </div>
        </div>

        <!-- Stories Grid -->
        <div id="stories-container" class="grid gap-6">
            <!-- Stories will be loaded here -->
        </div>

        <!-- Loading Indicator -->
        <div id="loading" class="text-center py-8 hidden">
            <i class="fas fa-spinner fa-spin text-2xl text-blue-600"></i>
            <p class="text-gray-500 mt-2">Loading stories...</p>
        </div>
    </div>

    <script>
        // JavaScript for dynamic loading and filtering
        let currentStories = [];
        
        async function loadStories() {
            const loading = document.getElementById('loading');
            const container = document.getElementById('stories-container');
            
            loading.classList.remove('hidden');
            
            try {
                const category = document.getElementById('category-filter').value;
                const source = document.getElementById('source-filter').value;
                const limit = document.getElementById('limit-filter').value;
                
                let url = `/api/summaries?limit=${limit}`;
                if (category) url += `&category=${encodeURIComponent(category)}`;
                if (source) url += `&source=${encodeURIComponent(source)}`;
                
                const response = await fetch(url);
                const stories = await response.json();
                
                currentStories = stories;
                renderStories(stories);
                
            } catch (error) {
                container.innerHTML = '<div class="text-center text-red-500 py-8">Error loading stories. Please try again.</div>';
            } finally {
                loading.classList.add('hidden');
            }
        }
        
        function renderStories(stories) {
            const container = document.getElementById('stories-container');
            
            if (stories.length === 0) {
                container.innerHTML = '<div class="text-center text-gray-500 py-8">No stories found matching your criteria.</div>';
                return;
            }
            
            container.innerHTML = stories.map(story => `
                <article class="bg-white rounded-lg shadow-md hover:shadow-lg transition-all duration-300 card-hover fade-in">
                    <div class="p-6">
                        <div class="flex items-start justify-between mb-4">
                            <div class="flex gap-2">
                                <span class="category-badge text-white text-xs px-2 py-1 rounded-full font-medium">
                                    ${story.category || 'General'}
                                </span>
                                <span class="source-badge text-white text-xs px-2 py-1 rounded-full font-medium">
                                    ${story.source || 'Unknown'}
                                </span>
                            </div>
                            <time class="text-sm text-gray-500" datetime="${story.published}">
                                ${formatDate(story.published)}
                            </time>
                        </div>
                        
                        <h2 class="text-xl font-bold text-gray-900 mb-3 leading-tight">
                            <a href="${story.url}" target="_blank" rel="noopener" 
                               class="hover:text-blue-600 transition-colors">
                                ${story.title}
                            </a>
                        </h2>
                        
                        <p class="text-gray-700 mb-4 leading-relaxed">
                            ${story.brief}
                        </p>
                        
                        <div class="flex items-center justify-between pt-4 border-t border-gray-100">
                            <a href="${story.url}" target="_blank" rel="noopener" 
                               class="inline-flex items-center text-blue-600 hover:text-blue-800 font-medium transition-colors">
                                Read Full Article
                                <i class="fas fa-external-link-alt ml-2 text-sm"></i>
                            </a>
                            <span class="text-xs text-gray-400">
                                Crawled: ${formatDate(story.crawled_at)}
                            </span>
                        </div>
                    </div>
                </article>
            `).join('');
        }
        
        function formatDate(dateString) {
            if (!dateString) return 'Unknown';
            const date = new Date(dateString);
            const now = new Date();
            const diff = now - date;
            const minutes = Math.floor(diff / 60000);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);
            
            if (minutes < 60) return `${minutes}m ago`;
            if (hours < 24) return `${hours}h ago`;
            if (days < 7) return `${days}d ago`;
            return date.toLocaleDateString();
        }
        
        // Event listeners
        document.getElementById('category-filter').addEventListener('change', loadStories);
        document.getElementById('source-filter').addEventListener('change', loadStories);
        document.getElementById('limit-filter').addEventListener('change', loadStories);
        document.getElementById('refresh-btn').addEventListener('click', loadStories);
        
        // Auto-refresh every 5 minutes
        setInterval(loadStories, 300000);
        
        // Load stories on page load
        document.addEventListener('DOMContentLoaded', loadStories);
    </script>
</body>
</html>
"""

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

# Web Interface
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Fancy web dashboard for viewing NIL news."""
    # Get stats for the dashboard
    stats = await stats_endpoint()
    categories = await categories()
    sources = await sources()
    
    # Use simple string replacement for template rendering
    html = HTML_TEMPLATE
    html = html.replace("{{ total_stories }}", str(stats["total_stories"]))
    html = html.replace("{{ stories_today }}", str(stats["stories_today"]))
    html = html.replace("{{ stories_week }}", str(stats["stories_this_week"]))
    html = html.replace("{{ active_feeds }}", str(stats["active_feeds"]))
    html = html.replace("{{ keywords_tracked }}", str(stats["keywords_tracked"]))
    
    # Replace categories
    cat_options = ""
    for cat in categories:
        cat_options += f'<option value="{cat["category"]}">{cat["category"]} ({cat["count"]})</option>'
    html = html.replace("{% for cat in categories %}<option value=\"{{ cat.category }}\">{{ cat.category }} ({{ cat.count }})</option>{% endfor %}", cat_options)
    
    # Replace sources
    source_options = ""
    for source in sources:
        source_options += f'<option value="{source["source"]}">{source["source"]} ({source["count"]})</option>'
    html = html.replace("{% for source in sources %}<option value=\"{{ source.source }}\">{{ source.source }} ({{ source.count }})</option>{% endfor %}", source_options)
    
    return html

# API endpoints (prefixed with /api/ for the web interface)
@app.get("/api/summaries")
async def api_summaries(limit: int = 50, category: str = None, source: str = None):
    """API version of summaries for the web interface."""
    return await summaries(limit, category, source)

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
        ORDER BY 
            CASE 
                WHEN published IS NOT NULL AND published != '' 
                THEN datetime(published) 
                ELSE datetime(crawled_at) 
            END DESC,
            datetime(crawled_at) DESC
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
        ORDER BY 
            CASE 
                WHEN published IS NOT NULL AND published != '' 
                THEN datetime(published) 
                ELSE datetime(crawled_at) 
            END DESC,
            datetime(crawled_at) DESC
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
async def stats_endpoint():
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
