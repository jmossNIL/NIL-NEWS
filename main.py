#!/usr/bin/env python3
"""
Enhanced NIL News Aggregator with Instagram, TikTok & Twitter Integration
"""
import os
import asyncio
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from typing import Any, Dict, List

import aiosqlite
import feedparser
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from trafilatura import extract
import httpx

# Enhanced Configuration
FEEDS = [
    "https://frontofficesports.com/feed/",
    "https://sportico.com/feed/",
    "https://businessofcollegesports.com/feed/",
    "https://www.espn.com/college-sports/rss",
    "https://sports.yahoo.com/college/rss",
    "https://www.si.com/college/.rss",
    "https://www.cbssports.com/rss/headlines/college-football/",
    "https://www.cbssports.com/rss/headlines/college-basketball/",
    "https://www.on3.com/nil/news/feed/",
    "https://www.athleticbusiness.com/rss/topic/college",
    "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=NIL+collective+booster&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=college+sports+transfer+portal&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=House+v+NCAA+NIL&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=NCAA+NIL+lawsuit&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=college+athlete+revenue+sharing&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=NIL+coach+comments&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=state+NIL+law+college&hl=en-US&gl=US&ceid=US:en",
]

KEYWORDS = [
    "nil", "name image likeness", "name, image and likeness", "nil deal", "nil collective",
    "collective", "booster", "endorsement", "sponsorship", "brand deal",
    "student-athlete", "college athlete", "transfer portal", "recruiting",
    "house v ncaa", "opendorse", "marketpryce", "revenue sharing",
    "salary cap", "antitrust", "injunction", "settlement", "lawsuit",
    "compliance", "ncaa", "conference commissioner", "roster limits",
]

TOPIC_PATTERNS = {
    "Legal": ["lawsuit", "settlement", "antitrust", "judge", "injunction", "complaint", "legal"],
    "Collectives": ["collective", "booster", "foundation", "donor"],
    "Technology": ["platform", "marketplace", "app", "software", "analytics"],
    "Recruiting": ["transfer portal", "recruiting", "signing", "commitment"],
    "Policy": ["ncaa", "compliance", "state law", "legislation", "congress", "rule"],
    "Finance": ["revenue sharing", "cap", "valuation", "funding", "contract", "deal"],
}

ENTITY_PATTERNS = {
    "players": [
        "caitlin clark", "livvy dunne", "arch manning", "bronny james", "cooper flagg",
        "shedeur sanders", "travis hunter", "angel reese", "paige bueckers", "hansel emmanuel",
    ],
    "coaches": [
        "deion sanders", "nick saban", "kirby smart", "dabo swinney", "dan lanning",
        "mike norvell", "jimbo fisher", "lane kiffin", "john calipari", "dawn staley",
    ],
    "schools": [
        "alabama", "georgia", "lsu", "michigan", "ohio state", "usc", "texas", "oklahoma",
        "florida state", "clemson", "oregon", "miami", "tennessee", "colorado", "uconn",
    ],
    "lawsuits": [
        "house v ncaa", "johnson v ncaa", "alston", "antitrust", "title ix", "ninth circuit",
    ],
}

# NIL Twitter accounts to monitor
NIL_TWITTER_ACCOUNTS = [
    {"handle": "NILWire", "name": "NIL Wire"},
    {"handle": "On3NIL", "name": "On3 NIL"},
    {"handle": "FrontOfficeSpts", "name": "Front Office Sports"},
    {"handle": "OpendorseTeam", "name": "Opendorse"},
    {"handle": "MarketPryce", "name": "MarketPryce"},
    {"handle": "NILStore", "name": "NIL Store"},
    {"handle": "TheAthletic", "name": "The Athletic"},
    {"handle": "SInow", "name": "Sports Illustrated"},
]

# Instagram accounts to monitor (using RSS feeds via external services)
NIL_INSTAGRAM_ACCOUNTS = [
    {"handle": "livvydunne", "name": "Livvy Dunne"},
    {"handle": "cavindertwins", "name": "Cavinder Twins"},
    {"handle": "shedeursanders", "name": "Shedeur Sanders"},
    {"handle": "lsu.gymgirl", "name": "LSU Gymnast"},
    {"handle": "opendorse", "name": "Opendorse"},
    {"handle": "marketpryce", "name": "MarketPryce"},
    {"handle": "iconsourceapp", "name": "Icon Source"},
    {"handle": "nilstore", "name": "NIL Store"},
    {"handle": "espncollegesports", "name": "ESPN College Sports"},
    {"handle": "theathletic", "name": "The Athletic"},
]

# TikTok accounts to monitor
NIL_TIKTOK_ACCOUNTS = [
    {"handle": "livvydunne", "name": "Livvy Dunne"},
    {"handle": "cavindertwins", "name": "Cavinder Twins"},
    {"handle": "shedeursanders", "name": "Shedeur Sanders"},
    {"handle": "lsu.gymgirl", "name": "LSU Gymnast"},
    {"handle": "opendorse", "name": "Opendorse"},
    {"handle": "marketpryce", "name": "MarketPryce"},
    {"handle": "espncollegesports", "name": "ESPN College Sports"},
    {"handle": "bleacherreport", "name": "Bleacher Report"},
    {"handle": "sportscenter", "name": "SportsCenter"},
]

# Social media RSS feeds (using multiple nitter instances for reliability)
TWITTER_RSS_FEEDS = [
    f"https://nitter.net/{account['handle']}/rss" for account in NIL_TWITTER_ACCOUNTS[:5]
]

INSTAGRAM_RSS_FEEDS = [
    f"https://imginn.org/{account['handle']}/rss" for account in NIL_INSTAGRAM_ACCOUNTS[:8]
]

TIKTOK_RSS_FEEDS = [
    f"https://www.tiktok.com/@{account['handle']}/rss" for account in NIL_TIKTOK_ACCOUNTS[:8]
]

# Social media search feeds
TWITTER_SEARCH_FEEDS = [
    "https://nitter.net/search/rss?q=NIL%20college",
    "https://nitter.net/search/rss?q=NIL%20deal",
]

DB_PATH = "/tmp/nil_news.db"

# Crawl flags
crawl_in_progress = False
twitter_crawl_in_progress = False
instagram_crawl_in_progress = False
tiktok_crawl_in_progress = False

# Database setup
async def init_db():
    """Initialize database with all social media tables."""
    try:
        db = await aiosqlite.connect(DB_PATH)
        
        # Stories table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published TEXT,
                summary TEXT,
                brief TEXT,
                crawled_at TEXT NOT NULL,
                source TEXT,
                category TEXT,
                entities TEXT
            )
        """)

        # Lightweight migration for older DB versions
        try:
            await db.execute("ALTER TABLE stories ADD COLUMN entities TEXT")
        except Exception:
            pass
        
        # Twitter posts table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS twitter_posts (
                id TEXT PRIMARY KEY,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                url TEXT NOT NULL,
                published TEXT,
                crawled_at TEXT NOT NULL,
                source_type TEXT DEFAULT 'twitter'
            )
        """)
        
        # Instagram posts table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS instagram_posts (
                id TEXT PRIMARY KEY,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                url TEXT NOT NULL,
                published TEXT,
                crawled_at TEXT NOT NULL,
                source_type TEXT DEFAULT 'instagram'
            )
        """)
        
        # TikTok posts table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tiktok_posts (
                id TEXT PRIMARY KEY,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                url TEXT NOT NULL,
                published TEXT,
                crawled_at TEXT NOT NULL,
                source_type TEXT DEFAULT 'tiktok'
            )
        """)
        
        await db.commit()
        await db.close()
        print("[info] Database initialized successfully with all social media tables")
        
    except Exception as e:
        print(f"[error] Database initialization failed: {e}")
        raise

# Content processing functions
def is_relevant(text: str) -> bool:
    """Simple but effective relevance checking."""
    text_lower = text.lower()
    keywords_lower = [k.lower() for k in KEYWORDS]
    return any(keyword in text_lower for keyword in keywords_lower)

def categorize_content(title: str, text: str) -> str:
    """Categorize story based on dominant NIL topic."""
    combined = (title + " " + text).lower()

    scored_topics = {}
    for topic, patterns in TOPIC_PATTERNS.items():
        score = sum(1 for pattern in patterns if pattern in combined)
        if score:
            scored_topics[topic] = score

    if not scored_topics:
        return "General"

    return max(scored_topics, key=scored_topics.get)


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract key NIL entities for dashboard filtering."""
    text_lower = text.lower()
    found: Dict[str, List[str]] = {"players": [], "coaches": [], "schools": [], "lawsuits": []}

    for entity_type, candidates in ENTITY_PATTERNS.items():
        for candidate in candidates:
            if candidate in text_lower:
                found[entity_type].append(candidate.title())

    # Fallback lightweight proper-noun detection for additional names.
    if not found["players"] and not found["coaches"]:
        names = re.findall(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", text)
        for name in names[:5]:
            if name not in found["players"]:
                found["players"].append(name)

    return found

def extract_source(url: str) -> str:
    """Simple source extraction."""
    try:
        if "frontofficesports.com" in url:
            return "Front Office Sports"
        elif "sportico.com" in url:
            return "Sportico"
        elif "businessofcollegesports.com" in url:
            return "Business of College Sports"
        elif "espn.com" in url:
            return "ESPN"
        elif "si.com" in url:
            return "Sports Illustrated"
        elif "news.google.com" in url:
            return "Google News"
        else:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            return domain.replace("www.", "").replace(".com", "").title()
    except:
        return "Unknown"

def simple_summarize(text: str) -> str:
    """Simple but effective summarization."""
    if not text:
        return "No summary available"
    
    text = text.replace('\n', ' ').strip()
    sentences = [s.strip() + '.' for s in text.split('.') if len(s.strip()) > 30]
    summary = ' '.join(sentences[:3])
    
    if len(summary) > 400:
        summary = summary[:400] + "..."
    
    return summary if summary else "Summary not available"

# Crawler functions
async def crawl_feeds():
    """Simple, reliable feed crawling."""
    global crawl_in_progress
    
    if crawl_in_progress:
        print("[info] Crawl already in progress, skipping")
        return
    
    crawl_in_progress = True
    print("[info] Starting feed crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        stories_added = 0
        
        async with httpx.AsyncClient(timeout=10.0, headers={'User-Agent': 'NIL-News-Bot/1.0'}) as client:
            for feed_url in FEEDS:
                try:
                    print(f"[info] Crawling {feed_url}")
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        print(f"[warn] HTTP {response.status_code} for {feed_url}")
                        continue
                        
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        print(f"[warn] No entries found in {feed_url}")
                        continue
                    
                    for entry in feed.entries[:5]:
                        if await process_entry(entry, db):
                            stories_added += 1
                            
                except Exception as e:
                    print(f"[error] Failed to process {feed_url}: {e}")
                    continue
        
        await db.close()
        print(f"[info] Crawl completed. Added {stories_added} new stories.")
        
    except Exception as e:
        print(f"[error] Crawl failed: {e}")
    finally:
        crawl_in_progress = False

async def process_entry(entry: dict, db) -> bool:
    """Simple, reliable entry processing."""
    try:
        url = entry.get("link")
        if not url:
            return False
        
        story_id = hashlib.sha256(url.encode()).hexdigest()
        async with db.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)) as cur:
            if await cur.fetchone():
                return False
        
        title = entry.get("title", "No title")
        
        # Get content with better fallback
        text = ""
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={'User-Agent': 'NIL-News-Bot/1.0'}) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    text = extract(response.text) or response.text[:1000]
        except:
            pass
        
        if not text:
            text = entry.get("summary", "") + " " + entry.get("description", "")
        
        if not text:
            return False
        
        if not is_relevant(title + " " + text):
            return False
        
        brief = simple_summarize(text)
        source = extract_source(url)
        category = categorize_content(title, text)
        entities = extract_entities(title + " " + text)
        published = entry.get("published", "")
        crawled_at = dt.datetime.utcnow().isoformat()

        await db.execute("""
            INSERT INTO stories (id, title, url, published, summary, brief, crawled_at, source, category, entities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            story_id,
            title,
            url,
            published,
            text[:2000],
            brief,
            crawled_at,
            source,
            category,
            json.dumps(entities),
        ))
        
        await db.commit()
        print(f"[+] Stored: {title[:50]}... [{source}]")
        return True
        
    except Exception as e:
        print(f"[error] Failed to process entry: {e}")
        return False

async def crawl_twitter_feeds():
    """Crawl Twitter RSS feeds for NIL content."""
    global twitter_crawl_in_progress
    
    if twitter_crawl_in_progress:
        print("[info] Twitter crawl already in progress, skipping")
        return
    
    twitter_crawl_in_progress = True
    print("[info] Starting Twitter feed crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        tweets_added = 0
        
        all_twitter_feeds = TWITTER_RSS_FEEDS + TWITTER_SEARCH_FEEDS
        
        async with httpx.AsyncClient(timeout=8.0, headers={'User-Agent': 'NIL-News-Bot/1.0'}) as client:
            for feed_url in all_twitter_feeds:
                try:
                    print(f"[info] Crawling Twitter feed: {feed_url}")
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        print(f"[warn] HTTP {response.status_code} for {feed_url}")
                        continue
                        
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        print(f"[warn] No Twitter entries found in {feed_url}")
                        continue
                    
                    for entry in feed.entries[:2]:
                        if await process_social_entry(entry, db, "twitter"):
                            tweets_added += 1
                            
                except Exception as e:
                    print(f"[error] Failed to process Twitter feed {feed_url}: {e}")
                    continue
        
        await db.close()
        print(f"[info] Twitter crawl completed. Added {tweets_added} new tweets.")
        
    except Exception as e:
        print(f"[error] Twitter crawl failed: {e}")
    finally:
        twitter_crawl_in_progress = False

async def crawl_instagram_feeds():
    """Crawl Instagram RSS feeds for NIL content."""
    global instagram_crawl_in_progress
    
    if instagram_crawl_in_progress:
        print("[info] Instagram crawl already in progress, skipping")
        return
    
    instagram_crawl_in_progress = True
    print("[info] Starting Instagram feed crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        posts_added = 0
        
        async with httpx.AsyncClient(timeout=8.0, headers={'User-Agent': 'NIL-News-Bot/1.0'}) as client:
            for feed_url in INSTAGRAM_RSS_FEEDS:
                try:
                    print(f"[info] Crawling Instagram feed: {feed_url}")
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        print(f"[warn] HTTP {response.status_code} for {feed_url}")
                        continue
                        
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        print(f"[warn] No Instagram entries found in {feed_url}")
                        continue
                    
                    for entry in feed.entries[:3]:
                        if await process_social_entry(entry, db, "instagram"):
                            posts_added += 1
                            
                except Exception as e:
                    print(f"[error] Failed to process Instagram feed {feed_url}: {e}")
                    continue
        
        await db.close()
        print(f"[info] Instagram crawl completed. Added {posts_added} new posts.")
        
    except Exception as e:
        print(f"[error] Instagram crawl failed: {e}")
    finally:
        instagram_crawl_in_progress = False

async def crawl_tiktok_feeds():
    """Crawl TikTok RSS feeds for NIL content."""
    global tiktok_crawl_in_progress
    
    if tiktok_crawl_in_progress:
        print("[info] TikTok crawl already in progress, skipping")
        return
    
    tiktok_crawl_in_progress = True
    print("[info] Starting TikTok feed crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        posts_added = 0
        
        async with httpx.AsyncClient(timeout=8.0, headers={'User-Agent': 'NIL-News-Bot/1.0'}) as client:
            for feed_url in TIKTOK_RSS_FEEDS:
                try:
                    print(f"[info] Crawling TikTok feed: {feed_url}")
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        print(f"[warn] HTTP {response.status_code} for {feed_url}")
                        continue
                        
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        print(f"[warn] No TikTok entries found in {feed_url}")
                        continue
                    
                    for entry in feed.entries[:3]:
                        if await process_social_entry(entry, db, "tiktok"):
                            posts_added += 1
                            
                except Exception as e:
                    print(f"[error] Failed to process TikTok feed {feed_url}: {e}")
                    continue
        
        await db.close()
        print(f"[info] TikTok crawl completed. Added {posts_added} new posts.")
        
    except Exception as e:
        print(f"[error] TikTok crawl failed: {e}")
    finally:
        tiktok_crawl_in_progress = False

async def process_social_entry(entry: dict, db, platform: str) -> bool:
    """Process a single social media entry."""
    try:
        url = entry.get("link")
        if not url:
            return False
        
        post_id = hashlib.sha256(url.encode()).hexdigest()
        table_name = f"{platform}_posts"
        
        async with db.execute(f"SELECT 1 FROM {table_name} WHERE id=?", (post_id,)) as cur:
            if await cur.fetchone():
                return False
        
        title = entry.get("title", "")
        content = entry.get("summary", "") or entry.get("description", "")
        
        if not is_relevant(title + " " + content):
            return False
        
        author = "Unknown"
        if ": " in title:
            author = title.split(": ")[0].strip()
            content = title.split(": ", 1)[1].strip()
        elif platform == "instagram" and "@" in title:
            author = title.split("@")[1].split()[0] if "@" in title else "Unknown"
        elif platform == "tiktok" and "by @" in title:
            author = title.split("by @")[1].split()[0] if "by @" in title else "Unknown"
        
        published = entry.get("published", "")
        crawled_at = dt.datetime.utcnow().isoformat()
        
        await db.execute(f"""
            INSERT INTO {table_name} (id, author, content, url, published, crawled_at, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (post_id, author, content, url, published, crawled_at, platform))
        
        await db.commit()
        print(f"[+] Stored {platform} post: @{author}: {content[:50]}...")
        return True
        
    except Exception as e:
        print(f"[error] Failed to process {platform} entry: {e}")
        return False

# FastAPI app
app = FastAPI(title="NIL News Hub Pro", version="4.1.0")

# Enhanced HTML template with four tabs
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIL News Hub Pro</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .card-hover:hover { transform: translateY(-2px); transition: all 0.3s; }
        .tab-active { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .tab-content.hidden { display: none; }
        .instagram-gradient { background: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%); }
        .tiktok-dark { background: linear-gradient(135deg, #000000 0%, #ff0050 100%); }
    </style>
</head>
<body class="bg-gray-50">
    <!-- Header -->
    <header class="gradient-bg text-white py-8">
        <div class="container mx-auto px-6">
            <h1 class="text-4xl font-bold mb-2">
                <i class="fas fa-newspaper mr-3"></i>NIL News Hub Pro
            </h1>
            <p class="text-blue-100">Complete NIL monitoring across all platforms</p>
            <p class="text-blue-200 text-sm mt-1">Live intelligence on players, coaches, schools, collectives, and lawsuits</p>
        </div>
    </header>

    <!-- Tabs -->
    <div class="container mx-auto px-6 pt-6">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6" id="metrics-grid">
            <div class="bg-white rounded-lg shadow-md p-4"><p class="text-xs text-gray-500 uppercase">Stories (total)</p><p id="metric-total" class="text-2xl font-bold text-gray-900">0</p></div>
            <div class="bg-white rounded-lg shadow-md p-4"><p class="text-xs text-gray-500 uppercase">Last 72h</p><p id="metric-recent" class="text-2xl font-bold text-blue-700">0</p></div>
            <div class="bg-white rounded-lg shadow-md p-4"><p class="text-xs text-gray-500 uppercase">Top Category</p><p id="metric-top-category" class="text-2xl font-bold text-purple-700">-</p></div>
            <div class="bg-white rounded-lg shadow-md p-4"><p class="text-xs text-gray-500 uppercase">Top Source</p><p id="metric-top-source" class="text-2xl font-bold text-emerald-700">-</p></div>
        </div>
        <div class="bg-white rounded-lg shadow-md mb-6">
            <div class="flex border-b overflow-x-auto">
                <button onclick="showTab('news')" id="news-tab" class="tab-active px-6 py-3 font-medium rounded-tl-lg flex-shrink-0">
                    <i class="fas fa-newspaper mr-2"></i>News Feed
                </button>
                <button onclick="showTab('twitter')" id="twitter-tab" class="px-6 py-3 font-medium hover:bg-gray-50 flex-shrink-0">
                    <i class="fab fa-twitter mr-2"></i>Twitter
                </button>
                <button onclick="showTab('instagram')" id="instagram-tab" class="px-6 py-3 font-medium hover:bg-gray-50 flex-shrink-0">
                    <i class="fab fa-instagram mr-2"></i>Instagram
                </button>
                <button onclick="showTab('tiktok')" id="tiktok-tab" class="px-6 py-3 font-medium hover:bg-gray-50 rounded-tr-lg flex-shrink-0">
                    <i class="fab fa-tiktok mr-2"></i>TikTok
                </button>
            </div>
        </div>

        <!-- News Tab -->
        <div id="news-content" class="tab-content">
            <div class="bg-white rounded-lg shadow-md p-4 mb-6">
                <div class="flex gap-4 items-center flex-wrap">
                    <button onclick="refreshStories()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-refresh mr-2"></i>Refresh Stories
                    </button>
                    <button onclick="crawlNow()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-download mr-2"></i>Crawl Now
                    </button>
                    <select id="category-filter" onchange="filterStories()" class="border border-gray-300 rounded-lg px-3 py-2">
                        <option value="">All Categories</option>
                        <option value="Legal">Legal</option>
                        <option value="Collectives">Collectives</option>
                        <option value="Technology">Technology</option>
                        <option value="Recruiting">Recruiting</option>
                        <option value="General">General</option>
                    </select>
                    <input id="search-filter" oninput="filterStories()" placeholder="Search NIL stories, schools, lawsuits..." class="border border-gray-300 rounded-lg px-3 py-2 min-w-[260px]" />
                    <select id="entity-filter" onchange="filterStories()" class="border border-gray-300 rounded-lg px-3 py-2">
                        <option value="">All Entities</option>
                    </select>
                    <span id="story-count" class="text-gray-600 font-medium"></span>
                </div>
            </div>
            <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div id="stories-container" class="xl:col-span-2">
                    <div class="text-center py-8">
                        <i class="fas fa-spinner fa-spin text-2xl text-blue-600"></i>
                        <p class="text-gray-600 mt-2">Loading NIL news...</p>
                    </div>
                </div>
                <aside class="bg-white rounded-lg shadow-md p-5 h-fit">
                    <h3 class="text-lg font-bold text-gray-900 mb-3"><i class="fas fa-chart-line mr-2"></i>NIL Intelligence</h3>
                    <div class="mb-4">
                        <h4 class="text-sm font-semibold text-gray-700 mb-2">Top Entities</h4>
                        <div id="entity-leaderboard" class="space-y-2 text-sm text-gray-700"></div>
                    </div>
                    <div>
                        <h4 class="text-sm font-semibold text-gray-700 mb-2">Top Sources</h4>
                        <div id="source-leaderboard" class="space-y-2 text-sm text-gray-700"></div>
                    </div>
                </aside>
            </div>
        </div>

        <!-- Twitter Tab -->
        <div id="twitter-content" class="tab-content hidden">
            <div class="bg-white rounded-lg shadow-md p-4 mb-6">
                <div class="flex gap-4 items-center flex-wrap">
                    <button onclick="refreshTwitter()" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg">
                        <i class="fab fa-twitter mr-2"></i>Refresh Twitter
                    </button>
                    <button onclick="crawlTwitterNow()" class="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-search mr-2"></i>Crawl Twitter
                    </button>
                    <span id="twitter-count" class="text-gray-600 font-medium"></span>
                </div>
            </div>
            <div id="twitter-container">
                <div class="text-center py-8">
                    <i class="fas fa-spinner fa-spin text-2xl text-blue-600"></i>
                    <p class="text-gray-600 mt-2">Loading Twitter feed...</p>
                </div>
            </div>
        </div>

        <!-- Instagram Tab -->
        <div id="instagram-content" class="tab-content hidden">
            <div class="bg-white rounded-lg shadow-md p-4 mb-6">
                <div class="flex gap-4 items-center flex-wrap">
                    <button onclick="refreshInstagram()" class="text-white px-4 py-2 rounded-lg instagram-gradient hover:opacity-90">
                        <i class="fab fa-instagram mr-2"></i>Refresh Instagram
                    </button>
                    <button onclick="crawlInstagramNow()" class="bg-pink-600 hover:bg-pink-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-camera mr-2"></i>Crawl Instagram
                    </button>
                    <span id="instagram-count" class="text-gray-600 font-medium"></span>
                </div>
            </div>
            <div id="instagram-container">
                <div class="text-center py-8">
                    <i class="fas fa-spinner fa-spin text-2xl text-pink-600"></i>
                    <p class="text-gray-600 mt-2">Loading Instagram feed...</p>
                </div>
            </div>
        </div>

        <!-- TikTok Tab -->
        <div id="tiktok-content" class="tab-content hidden">
            <div class="bg-white rounded-lg shadow-md p-4 mb-6">
                <div class="flex gap-4 items-center flex-wrap">
                    <button onclick="refreshTikTok()" class="text-white px-4 py-2 rounded-lg tiktok-dark hover:opacity-90">
                        <i class="fab fa-tiktok mr-2"></i>Refresh TikTok
                    </button>
                    <button onclick="crawlTikTokNow()" class="bg-gray-800 hover:bg-gray-900 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-video mr-2"></i>Crawl TikTok
                    </button>
                    <span id="tiktok-count" class="text-gray-600 font-medium"></span>
                </div>
            </div>
            <div id="tiktok-container">
                <div class="text-center py-8">
                    <i class="fas fa-spinner fa-spin text-2xl text-gray-800"></i>
                    <p class="text-gray-600 mt-2">Loading TikTok feed...</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let allStories = [];
        let allTweets = [];
        let allInstagramPosts = [];
        let allTikTokPosts = [];
        let currentTab = 'news';
        let analyticsData = null;

        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('[id$="-tab"]').forEach(el => {
                el.classList.remove('tab-active');
                el.classList.add('hover:bg-gray-50');
            });
            
            document.getElementById(tabName + '-content').classList.remove('hidden');
            const activeTab = document.getElementById(tabName + '-tab');
            activeTab.classList.add('tab-active');
            activeTab.classList.remove('hover:bg-gray-50');
            
            currentTab = tabName;
            
            if (tabName === 'twitter') {
                loadTwitterPosts();
            } else if (tabName === 'instagram') {
                loadInstagramPosts();
            } else if (tabName === 'tiktok') {
                loadTikTokPosts();
            }
        }

        async function loadAnalytics() {
            try {
                const response = await fetch('/api/analytics?hours=72');
                if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

                analyticsData = await response.json();
                document.getElementById('metric-total').textContent = analyticsData.stories_total || 0;
                document.getElementById('metric-recent').textContent = analyticsData.stories_last_window || 0;

                const categoryEntries = Object.entries(analyticsData.category_breakdown || {});
                const topCategory = categoryEntries.length ? categoryEntries[0][0] : '-';
                document.getElementById('metric-top-category').textContent = topCategory;

                const topSource = (analyticsData.top_sources || [])[0]?.source || '-';
                document.getElementById('metric-top-source').textContent = topSource;

                const leaderboard = document.getElementById('entity-leaderboard');
                const allEntities = [];
                const sections = ['players', 'coaches', 'schools', 'lawsuits'];
                const lines = [];
                sections.forEach(section => {
                    (analyticsData.entity_leaders?.[section] || []).slice(0, 2).forEach(item => {
                        lines.push(`<div class="flex justify-between"><span class="capitalize">${item.name}</span><span class="text-gray-500">${item.count}</span></div>`);
                        allEntities.push(item.name);
                    });
                });
                leaderboard.innerHTML = lines.length ? lines.join('') : '<p class="text-gray-500">No entities yet.</p>';

                const sourceBoard = document.getElementById('source-leaderboard');
                sourceBoard.innerHTML = (analyticsData.top_sources || []).slice(0, 6).map(item =>
                    `<div class="flex justify-between"><span>${item.source}</span><span class="text-gray-500">${item.count}</span></div>`
                ).join('') || '<p class="text-gray-500">No sources yet.</p>';

                const entityFilter = document.getElementById('entity-filter');
                const existingValue = entityFilter.value;
                const uniqueEntities = [...new Set(allEntities)].sort((a, b) => a.localeCompare(b));
                entityFilter.innerHTML = '<option value="">All Entities</option>' +
                    uniqueEntities.map(name => `<option value="${name}">${name}</option>`).join('');
                entityFilter.value = uniqueEntities.includes(existingValue) ? existingValue : '';

            } catch (error) {
                console.error('Error loading analytics:', error);
            }
        }

        async function loadStories() {
            try {
                const response = await fetch('/api/summaries?limit=50');
                if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                
                const stories = await response.json();
                allStories = stories;
                document.getElementById('story-count').textContent = `${stories.length} stories loaded`;
                filterStories();
                
            } catch (error) {
                console.error('Error loading stories:', error);
                document.getElementById('stories-container').innerHTML = 
                    `<div class="text-center text-red-500 py-8">
                        <p>Error loading stories: ${error.message}</p>
                        <button onclick="refreshStories()" class="mt-4 bg-blue-600 text-white px-4 py-2 rounded">
                            Try Again
                        </button>
                    </div>`;
            }
        }

        function filterStories() {
            const categoryFilter = document.getElementById('category-filter').value;
            const searchFilter = (document.getElementById('search-filter').value || '').toLowerCase();
            const entityFilter = (document.getElementById('entity-filter').value || '').toLowerCase();

            let filteredStories = allStories.filter(story => {
                if (categoryFilter && story.category !== categoryFilter) return false;

                const searchable = `${story.title} ${story.brief} ${story.source}`.toLowerCase();
                if (searchFilter && !searchable.includes(searchFilter)) return false;

                if (entityFilter) {
                    const entityValues = Object.values(story.entities || {}).flat().map(value => value.toLowerCase());
                    if (!entityValues.includes(entityFilter)) return false;
                }
                return true;
            });

            filteredStories.sort((a, b) => {
                const dateA = new Date(a.published || a.crawled_at || 0);
                const dateB = new Date(b.published || b.crawled_at || 0);
                return dateB - dateA;
            });

            const container = document.getElementById('stories-container');
            
            if (filteredStories.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <i class="fas fa-newspaper text-4xl text-gray-400 mb-4"></i>
                        <p class="text-gray-600 text-lg">No stories found.</p>
                        <p class="text-gray-500">Click "Crawl Now" to fetch the latest NIL news!</p>
                        <button onclick="crawlNow()" class="mt-4 bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded-lg">
                            <i class="fas fa-download mr-2"></i>Get Stories
                        </button>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = filteredStories.map(story => `
                <article class="bg-white rounded-lg shadow-md hover:shadow-lg card-hover p-6 mb-6">
                    <div class="flex items-start justify-between mb-4">
                        <div class="flex gap-2">
                            <span class="bg-blue-500 text-white text-xs px-3 py-1 rounded-full font-medium">
                                ${story.category || 'General'}
                            </span>
                            <span class="bg-green-500 text-white text-xs px-3 py-1 rounded-full font-medium">
                                ${story.source || 'Unknown'}
                            </span>
                        </div>
                        <time class="text-sm text-gray-500">
                            ${formatDate(story.published || story.crawled_at)}
                        </time>
                    </div>
                    
                    <h2 class="text-xl font-bold text-gray-900 mb-3 leading-tight">
                        <a href="${story.url}" target="_blank" class="hover:text-blue-600 transition-colors">
                            ${story.title}
                        </a>
                    </h2>
                    
                    <p class="text-gray-700 mb-4 leading-relaxed">${story.brief}</p>
                    <div class="flex flex-wrap gap-2 mb-4">
                        ${Object.entries(story.entities || {}).flatMap(([kind, names]) =>
                            (names || []).slice(0, 3).map(name =>
                                `<span class="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded-full">${kind.slice(0, -1)}: ${name}</span>`
                            )
                        ).join('')}
                    </div>

                    <a href="${story.url}" target="_blank" 
                       class="inline-flex items-center text-blue-600 hover:text-blue-800 font-medium transition-colors">
                        Read Full Article
                        <i class="fas fa-external-link-alt ml-2 text-sm"></i>
                    </a>
                </article>
            `).join('');
        }

        async function loadTwitterPosts() {
            try {
                const response = await fetch('/api/twitter?limit=30');
                if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                
                const tweets = await response.json();
                allTweets = tweets;
                document.getElementById('twitter-count').textContent = `${tweets.length} tweets loaded`;
                renderTwitterPosts();
                
            } catch (error) {
                console.error('Error loading Twitter posts:', error);
                document.getElementById('twitter-container').innerHTML = 
                    `<div class="text-center text-red-500 py-8">
                        <p>Error loading Twitter feed: ${error.message}</p>
                        <button onclick="refreshTwitter()" class="mt-4 bg-blue-600 text-white px-4 py-2 rounded">
                            Try Again
                        </button>
                    </div>`;
            }
        }

        function renderTwitterPosts() {
            const container = document.getElementById('twitter-container');
            
            if (allTweets.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <i class="fab fa-twitter text-4xl text-blue-400 mb-4"></i>
                        <p class="text-gray-600 text-lg">No Twitter posts found.</p>
                        <p class="text-gray-500">Click "Crawl Twitter" to fetch the latest NIL tweets!</p>
                        <button onclick="crawlTwitterNow()" class="mt-4 bg-purple-600 hover:bg-purple-700 text-white px-6 py-2 rounded-lg">
                            <i class="fab fa-twitter mr-2"></i>Get Tweets
                        </button>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = allTweets.map(tweet => `
                <article class="bg-white rounded-lg shadow-md hover:shadow-lg card-hover p-6 mb-4">
                    <div class="flex items-start justify-between mb-3">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center">
                                <i class="fab fa-twitter text-white"></i>
                            </div>
                            <div>
                                <h3 class="font-bold text-gray-900">@${tweet.author}</h3>
                                <time class="text-sm text-gray-500">
                                    ${formatDate(tweet.published || tweet.crawled_at)}
                                </time>
                            </div>
                        </div>
                        <span class="bg-purple-500 text-white text-xs px-2 py-1 rounded-full">
                            Twitter
                        </span>
                    </div>
                    
                    <p class="text-gray-800 mb-4 leading-relaxed">${tweet.content}</p>
                    
                    <a href="${tweet.url}" target="_blank" 
                       class="inline-flex items-center text-blue-600 hover:text-blue-800 font-medium transition-colors">
                        View on Twitter
                        <i class="fas fa-external-link-alt ml-2 text-sm"></i>
                    </a>
                </article>
            `).join('');
        }

        async function loadInstagramPosts() {
            try {
                const response = await fetch('/api/instagram?limit=30');
                if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                
                const posts = await response.json();
                allInstagramPosts = posts;
                document.getElementById('instagram-count').textContent = `${posts.length} posts loaded`;
                renderInstagramPosts();
                
            } catch (error) {
                console.error('Error loading Instagram posts:', error);
                document.getElementById('instagram-container').innerHTML = 
                    `<div class="text-center text-red-500 py-8">
                        <p>Error loading Instagram feed: ${error.message}</p>
                        <button onclick="refreshInstagram()" class="mt-4 bg-pink-600 text-white px-4 py-2 rounded">
                            Try Again
                        </button>
                    </div>`;
            }
        }

        function renderInstagramPosts() {
            const container = document.getElementById('instagram-container');
            
            if (allInstagramPosts.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <i class="fab fa-instagram text-4xl text-pink-500 mb-4"></i>
                        <p class="text-gray-600 text-lg">No Instagram posts found.</p>
                        <p class="text-gray-500">Click "Crawl Instagram" to fetch the latest NIL posts!</p>
                        <button onclick="crawlInstagramNow()" class="mt-4 bg-pink-600 hover:bg-pink-700 text-white px-6 py-2 rounded-lg">
                            <i class="fab fa-instagram mr-2"></i>Get Posts
                        </button>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = allInstagramPosts.map(post => `
                <article class="bg-white rounded-lg shadow-md hover:shadow-lg card-hover p-6 mb-4">
                    <div class="flex items-start justify-between mb-3">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 instagram-gradient rounded-full flex items-center justify-center">
                                <i class="fab fa-instagram text-white"></i>
                            </div>
                            <div>
                                <h3 class="font-bold text-gray-900">@${post.author}</h3>
                                <time class="text-sm text-gray-500">
                                    ${formatDate(post.published || post.crawled_at)}
                                </time>
                            </div>
                        </div>
                        <span class="bg-pink-500 text-white text-xs px-2 py-1 rounded-full">
                            Instagram
                        </span>
                    </div>
                    
                    <p class="text-gray-800 mb-4 leading-relaxed">${post.content}</p>
                    
                    <a href="${post.url}" target="_blank" 
                       class="inline-flex items-center text-pink-600 hover:text-pink-800 font-medium transition-colors">
                        View on Instagram
                        <i class="fas fa-external-link-alt ml-2 text-sm"></i>
                    </a>
                </article>
            `).join('');
        }

        async function loadTikTokPosts() {
            try {
                const response = await fetch('/api/tiktok?limit=30');
                if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                
                const posts = await response.json();
                allTikTokPosts = posts;
                document.getElementById('tiktok-count').textContent = `${posts.length} videos loaded`;
                renderTikTokPosts();
                
            } catch (error) {
                console.error('Error loading TikTok posts:', error);
                document.getElementById('tiktok-container').innerHTML = 
                    `<div class="text-center text-red-500 py-8">
                        <p>Error loading TikTok feed: ${error.message}</p>
                        <button onclick="refreshTikTok()" class="mt-4 bg-gray-800 text-white px-4 py-2 rounded">
                            Try Again
                        </button>
                    </div>`;
            }
        }

        function renderTikTokPosts() {
            const container = document.getElementById('tiktok-container');
            
            if (allTikTokPosts.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <i class="fab fa-tiktok text-4xl text-gray-800 mb-4"></i>
                        <p class="text-gray-600 text-lg">No TikTok videos found.</p>
                        <p class="text-gray-500">Click "Crawl TikTok" to fetch the latest NIL videos!</p>
                        <button onclick="crawlTikTokNow()" class="mt-4 bg-gray-800 hover:bg-gray-900 text-white px-6 py-2 rounded-lg">
                            <i class="fab fa-tiktok mr-2"></i>Get Videos
                        </button>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = allTikTokPosts.map(post => `
                <article class="bg-white rounded-lg shadow-md hover:shadow-lg card-hover p-6 mb-4">
                    <div class="flex items-start justify-between mb-3">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 tiktok-dark rounded-full flex items-center justify-center">
                                <i class="fab fa-tiktok text-white"></i>
                            </div>
                            <div>
                                <h3 class="font-bold text-gray-900">@${post.author}</h3>
                                <time class="text-sm text-gray-500">
                                    ${formatDate(post.published || post.crawled_at)}
                                </time>
                            </div>
                        </div>
                        <span class="bg-gray-800 text-white text-xs px-2 py-1 rounded-full">
                            TikTok
                        </span>
                    </div>
                    
                    <p class="text-gray-800 mb-4 leading-relaxed">${post.content}</p>
                    
                    <a href="${post.url}" target="_blank" 
                       class="inline-flex items-center text-gray-800 hover:text-gray-900 font-medium transition-colors">
                        Watch on TikTok
                        <i class="fas fa-external-link-alt ml-2 text-sm"></i>
                    </a>
                </article>
            `).join('');
        }
        
        async function refreshStories() {
            await loadStories();
        }

        async function refreshTwitter() {
            await loadTwitterPosts();
        }

        async function refreshInstagram() {
            await loadInstagramPosts();
        }

        async function refreshTikTok() {
            await loadTikTokPosts();
        }
        
        async function crawlNow() {
            try {
                const button = document.querySelector('button[onclick="crawlNow()"]');
                button.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Crawling...';
                button.disabled = true;
                
                const response = await fetch('/api/crawl', { method: 'POST' });
                
                if (response.ok) {
                    alert('Crawl started! Check back in 2-3 minutes for new stories.');
                } else {
                    alert('Error starting crawl. Please try again.');
                }
                
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                const button = document.querySelector('button[onclick="crawlNow()"]');
                button.innerHTML = '<i class="fas fa-download mr-2"></i>Crawl Now';
                button.disabled = false;
            }
        }

        async function crawlTwitterNow() {
            try {
                const button = document.querySelector('button[onclick="crawlTwitterNow()"]');
                button.innerHTML = '<i class="fab fa-twitter fa-spin mr-2"></i>Crawling...';
                button.disabled = true;
                
                const response = await fetch('/api/crawl-twitter', { method: 'POST' });
                
                if (response.ok) {
                    alert('Twitter crawl started! Check back in 1-2 minutes for new tweets.');
                } else {
                    alert('Error starting Twitter crawl. Please try again.');
                }
                
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                const button = document.querySelector('button[onclick="crawlTwitterNow()"]');
                button.innerHTML = '<i class="fas fa-search mr-2"></i>Crawl Twitter';
                button.disabled = false;
            }
        }

        async function crawlInstagramNow() {
            try {
                const button = document.querySelector('button[onclick="crawlInstagramNow()"]');
                button.innerHTML = '<i class="fab fa-instagram fa-spin mr-2"></i>Crawling...';
                button.disabled = true;
                
                const response = await fetch('/api/crawl-instagram', { method: 'POST' });
                
                if (response.ok) {
                    alert('Instagram crawl started! Check back in 1-2 minutes for new posts.');
                } else {
                    alert('Error starting Instagram crawl. Please try again.');
                }
                
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                const button = document.querySelector('button[onclick="crawlInstagramNow()"]');
                button.innerHTML = '<i class="fas fa-camera mr-2"></i>Crawl Instagram';
                button.disabled = false;
            }
        }

        async function crawlTikTokNow() {
            try {
                const button = document.querySelector('button[onclick="crawlTikTokNow()"]');
                button.innerHTML = '<i class="fab fa-tiktok fa-spin mr-2"></i>Crawling...';
                button.disabled = true;
                
                const response = await fetch('/api/crawl-tiktok', { method: 'POST' });
                
                if (response.ok) {
                    alert('TikTok crawl started! Check back in 1-2 minutes for new videos.');
                } else {
                    alert('Error starting TikTok crawl. Please try again.');
                }
                
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                const button = document.querySelector('button[onclick="crawlTikTokNow()"]');
                button.innerHTML = '<i class="fas fa-video mr-2"></i>Crawl TikTok';
                button.disabled = false;
            }
        }
        
        function formatDate(dateString) {
            if (!dateString) return 'Unknown';
            try {
                const date = new Date(dateString);
                const now = new Date();
                const diff = now - date;
                const hours = Math.floor(diff / (1000 * 60 * 60));
                const days = Math.floor(hours / 24);
                
                if (hours < 1) return 'Just now';
                if (hours < 24) return `${hours}h ago`;
                if (days < 7) return `${days}d ago`;
                return date.toLocaleDateString();
            } catch {
                return 'Unknown';
            }
        }
        
        loadAnalytics();
        loadStories();
        
        setInterval(() => {
            if (currentTab === 'news') {
                loadAnalytics();
                loadStories();
            } else if (currentTab === 'twitter') {
                loadTwitterPosts();
            } else if (currentTab === 'instagram') {
                loadInstagramPosts();
            } else if (currentTab === 'tiktok') {
                loadTikTokPosts();
            }
        }, 300000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Enhanced web dashboard with four tabs."""
    return HTML_TEMPLATE

@app.get("/api/summaries")
async def get_summaries(limit: int = 50, q: str = "", entity: str = ""):
    """Get story summaries with bulletproof error handling."""
    try:
        if not os.path.exists(DB_PATH):
            return []
        
        db = await aiosqlite.connect(DB_PATH)
        
        async with db.execute("""
            SELECT title, url, published, brief, source, category, crawled_at, entities
            FROM stories
            ORDER BY 
                CASE 
                    WHEN published IS NOT NULL AND published != '' 
                    THEN datetime(published) 
                    ELSE datetime(crawled_at) 
                END DESC
            LIMIT ?
        """, (max(limit * 4, 100),)) as cur:
            rows = await cur.fetchall()
        
        await db.close()
        
        stories = []
        for row in rows:
            try:
                entities_data = json.loads(row[7]) if row[7] else {"players": [], "coaches": [], "schools": [], "lawsuits": []}
                story = {
                    "title": str(row[0] or "No Title"),
                    "url": str(row[1] or ""),
                    "published": str(row[2] or ""),
                    "brief": str(row[3] or "No summary available"),
                    "source": str(row[4] or "Unknown"),
                    "category": str(row[5] or "General"),
                    "crawled_at": str(row[6] or ""),
                    "entities": entities_data,
                }

                searchable = f"{story['title']} {story['brief']} {story['source']}".lower()
                if q and q.lower() not in searchable:
                    continue

                if entity:
                    entity_lower = entity.lower()
                    entity_values = [v.lower() for values in entities_data.values() for v in values]
                    if entity_lower not in entity_values:
                        continue

                stories.append(story)
            except Exception as e:
                continue
        
        return stories[:limit]
        
    except Exception as e:
        print(f"[error] Database query failed: {e}")
        return []

@app.get("/api/analytics")
async def get_analytics(hours: int = 72):
    """Aggregate NIL intelligence metrics for dashboard widgets."""
    try:
        if not os.path.exists(DB_PATH):
            return {
                "stories_total": 0,
                "stories_last_window": 0,
                "category_breakdown": {},
                "top_sources": [],
                "entity_leaders": {"players": [], "coaches": [], "schools": [], "lawsuits": []},
                "updated_at": dt.datetime.utcnow().isoformat(),
            }

        db = await aiosqlite.connect(DB_PATH)
        cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).isoformat()

        async with db.execute("SELECT COUNT(*) FROM stories") as cur:
            total_stories = (await cur.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM stories WHERE crawled_at >= ?", (cutoff,)) as cur:
            recent_stories = (await cur.fetchone())[0]

        async with db.execute("SELECT category, COUNT(*) FROM stories GROUP BY category ORDER BY COUNT(*) DESC") as cur:
            category_rows = await cur.fetchall()

        async with db.execute("SELECT source, COUNT(*) FROM stories GROUP BY source ORDER BY COUNT(*) DESC LIMIT 8") as cur:
            source_rows = await cur.fetchall()

        async with db.execute("SELECT entities FROM stories WHERE entities IS NOT NULL AND entities != ''") as cur:
            entity_rows = await cur.fetchall()

        await db.close()

        entity_counters = {
            "players": Counter(),
            "coaches": Counter(),
            "schools": Counter(),
            "lawsuits": Counter(),
        }
        for (entity_json,) in entity_rows:
            try:
                parsed = json.loads(entity_json)
                for entity_type in entity_counters.keys():
                    for name in parsed.get(entity_type, []):
                        entity_counters[entity_type][name] += 1
            except Exception:
                continue

        return {
            "stories_total": total_stories,
            "stories_last_window": recent_stories,
            "category_breakdown": {row[0] or "General": row[1] for row in category_rows},
            "top_sources": [{"source": row[0] or "Unknown", "count": row[1]} for row in source_rows],
            "entity_leaders": {
                key: [{"name": name, "count": count} for name, count in counter.most_common(6)]
                for key, counter in entity_counters.items()
            },
            "updated_at": dt.datetime.utcnow().isoformat(),
        }

    except Exception as e:
        print(f"[error] Analytics query failed: {e}")
        return {
            "stories_total": 0,
            "stories_last_window": 0,
            "category_breakdown": {},
            "top_sources": [],
            "entity_leaders": {"players": [], "coaches": [], "schools": [], "lawsuits": []},
            "updated_at": dt.datetime.utcnow().isoformat(),
        }

@app.get("/api/twitter")
async def get_twitter_posts(limit: int = 30):
    """Get Twitter posts with NIL content."""
    try:
        if not os.path.exists(DB_PATH):
            return []
        
        db = await aiosqlite.connect(DB_PATH)
        
        async with db.execute("""
            SELECT author, content, url, published, crawled_at
            FROM twitter_posts
            ORDER BY 
                CASE 
                    WHEN published IS NOT NULL AND published != '' 
                    THEN datetime(published) 
                    ELSE datetime(crawled_at) 
                END DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
        
        await db.close()
        
        tweets = []
        for row in rows:
            try:
                tweet = {
                    "author": str(row[0] or "Unknown"),
                    "content": str(row[1] or "No content"),
                    "url": str(row[2] or ""),
                    "published": str(row[3] or ""),
                    "crawled_at": str(row[4] or "")
                }
                tweets.append(tweet)
            except Exception as e:
                continue
        
        return tweets
        
    except Exception as e:
        print(f"[error] Twitter database query failed: {e}")
        return []

@app.get("/api/instagram")
async def get_instagram_posts(limit: int = 30):
    """Get Instagram posts with NIL content."""
    try:
        if not os.path.exists(DB_PATH):
            return []
        
        db = await aiosqlite.connect(DB_PATH)
        
        async with db.execute("""
            SELECT author, content, url, published, crawled_at
            FROM instagram_posts
            ORDER BY 
                CASE 
                    WHEN published IS NOT NULL AND published != '' 
                    THEN datetime(published) 
                    ELSE datetime(crawled_at) 
                END DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
        
        await db.close()
        
        posts = []
        for row in rows:
            try:
                post = {
                    "author": str(row[0] or "Unknown"),
                    "content": str(row[1] or "No content"),
                    "url": str(row[2] or ""),
                    "published": str(row[3] or ""),
                    "crawled_at": str(row[4] or "")
                }
                posts.append(post)
            except Exception as e:
                continue
        
        return posts
        
    except Exception as e:
        print(f"[error] Instagram database query failed: {e}")
        return []

@app.get("/api/tiktok")
async def get_tiktok_posts(limit: int = 30):
    """Get TikTok posts with NIL content."""
    try:
        if not os.path.exists(DB_PATH):
            return []
        
        db = await aiosqlite.connect(DB_PATH)
        
        async with db.execute("""
            SELECT author, content, url, published, crawled_at
            FROM tiktok_posts
            ORDER BY 
                CASE 
                    WHEN published IS NOT NULL AND published != '' 
                    THEN datetime(published) 
                    ELSE datetime(crawled_at) 
                END DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
        
        await db.close()
        
        posts = []
        for row in rows:
            try:
                post = {
                    "author": str(row[0] or "Unknown"),
                    "content": str(row[1] or "No content"),
                    "url": str(row[2] or ""),
                    "published": str(row[3] or ""),
                    "crawled_at": str(row[4] or "")
                }
                posts.append(post)
            except Exception as e:
                continue
        
        return posts
        
    except Exception as e:
        print(f"[error] TikTok database query failed: {e}")
        return []

@app.post("/api/crawl")
async def manual_crawl():
    """Trigger manual crawl."""
    try:
        asyncio.create_task(crawl_feeds())
        return {"status": "crawl started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/crawl-twitter")
async def manual_twitter_crawl():
    """Trigger manual Twitter crawl."""
    try:
        asyncio.create_task(crawl_twitter_feeds())
        return {"status": "twitter crawl started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/crawl-instagram")
async def manual_instagram_crawl():
    """Trigger manual Instagram crawl."""
    try:
        asyncio.create_task(crawl_instagram_feeds())
        return {"status": "instagram crawl started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/crawl-tiktok")
async def manual_tiktok_crawl():
    """Trigger manual TikTok crawl."""
    try:
        asyncio.create_task(crawl_tiktok_feeds())
        return {"status": "tiktok crawl started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/health")
async def health():
    """Health check."""
    try:
        if os.path.exists(DB_PATH):
            db = await aiosqlite.connect(DB_PATH)
            async with db.execute("SELECT COUNT(*) FROM stories") as cur:
                story_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM twitter_posts") as cur:
                twitter_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM instagram_posts") as cur:
                instagram_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM tiktok_posts") as cur:
                tiktok_count = (await cur.fetchone())[0]
            await db.close()
            return {
                "status": "healthy", 
                "stories": story_count,
                "twitter": twitter_count,
                "instagram": instagram_count,
                "tiktok": tiktok_count,
                "version": "4.1.0"
            }
        else:
            return {"status": "healthy", "stories": 0, "version": "4.1.0"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Enhanced background crawling
async def background_crawler():
    """Enhanced background crawler for all platforms."""
    # Do first crawl immediately
    print("[info] Starting initial crawls...")
    if not crawl_in_progress:
        await crawl_feeds()
    
    await asyncio.sleep(30)
    
    if not twitter_crawl_in_progress:
        await crawl_twitter_feeds()
    
    await asyncio.sleep(30)
    
    if not instagram_crawl_in_progress:
        await crawl_instagram_feeds()
    
    await asyncio.sleep(30)
    
    if not tiktok_crawl_in_progress:
        await crawl_tiktok_feeds()
    
    while True:
        try:
            await asyncio.sleep(300)  # Wait 5 minutes
            
            # Crawl all platforms sequentially
            if not crawl_in_progress:
                await crawl_feeds()
                await asyncio.sleep(30)
            
            if not twitter_crawl_in_progress:
                await crawl_twitter_feeds()
                await asyncio.sleep(30)
            
            if not instagram_crawl_in_progress:
                await crawl_instagram_feeds()
                await asyncio.sleep(30)
            
            if not tiktok_crawl_in_progress:
                await crawl_tiktok_feeds()
                
        except Exception as e:
            print(f"[error] Background crawler failed: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    """Start enhanced background tasks."""
    try:
        await init_db()
        asyncio.create_task(background_crawler())
        print("[info] NIL News Hub Pro started successfully with all social platforms")
    except Exception as e:
        print(f"[error] Startup failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
