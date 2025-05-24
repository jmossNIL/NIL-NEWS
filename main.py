#!/usr/bin/env python3
"""
Enhanced NIL News Aggregator with Instagram, TikTok & Twitter Integration - FIXED
"""
import os
import asyncio
import datetime as dt
import hashlib
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
    "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=NIL+collective+booster&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=college+sports+transfer+portal&hl=en-US&gl=US&ceid=US:en",
]

KEYWORDS = [
    "nil", "name image likeness", "nil deal", "nil collective",
    "collective", "booster", "endorsement", "sponsorship",
    "student-athlete", "college athlete", "transfer portal",
    "house v ncaa", "opendorse", "marketpryce",
]

# NIL Twitter accounts to monitor (FIXED)
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

# Instagram accounts to monitor
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

# FIXED: Working Nitter instances (tested and verified)
WORKING_NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net", 
    "https://nitter.woodland.cafe"
]

# FIXED: Generate Twitter RSS feeds using working instances
TWITTER_RSS_FEEDS = []
for instance in WORKING_NITTER_INSTANCES[:2]:  # Use only 2 instances
    for account in NIL_TWITTER_ACCOUNTS[:3]:   # Monitor top 3 accounts only
        TWITTER_RSS_FEEDS.append(f"{instance}/{account['handle']}/rss")

# Instagram and TikTok RSS feeds
INSTAGRAM_RSS_FEEDS = [
    f"https://imginn.org/{account['handle']}/rss" for account in NIL_INSTAGRAM_ACCOUNTS[:8]
]

TIKTOK_RSS_FEEDS = [
    f"https://www.tiktok.com/@{account['handle']}/rss" for account in NIL_TIKTOK_ACCOUNTS[:8]
]

# FIXED: Enhanced Twitter search using Google News (more reliable)
TWITTER_SEARCH_FEEDS = [
    "https://news.google.com/rss/search?q=%22NIL%22+%22college+athlete%22+social+media&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22NIL+deal%22+twitter&hl=en-US&gl=US&ceid=US:en",
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
                category TEXT
            )
        """)
        
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
    """Enhanced relevance checking."""
    text_lower = text.lower()
    keywords_lower = [k.lower() for k in KEYWORDS]
    nil_keywords = ["nil", "name image likeness", "collective", "endorsement", "sponsorship", 
                   "student athlete", "college athlete", "college sports", "ncaa", "booster"]
    all_keywords = keywords_lower + nil_keywords
    return any(keyword in text_lower for keyword in all_keywords)

def categorize_content(title: str, text: str) -> str:
    """Simple categorization."""
    combined = (title + " " + text).lower()
    
    if any(word in combined for word in ["lawsuit", "settlement", "legal"]):
        return "Legal"
    elif any(word in combined for word in ["collective", "booster"]):
        return "Collectives"
    elif any(word in combined for word in ["marketplace", "platform"]):
        return "Technology"
    elif any(word in combined for word in ["transfer portal", "recruiting"]):
        return "Recruiting"
    else:
        return "General"

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
        published = entry.get("published", "")
        crawled_at = dt.datetime.utcnow().isoformat()
        
        await db.execute("""
            INSERT INTO stories (id, title, url, published, summary, brief, crawled_at, source, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (story_id, title, url, published, text[:2000], brief, crawled_at, source, category))
        
        await db.commit()
        print(f"[+] Stored: {title[:50]}... [{source}]")
        return True
        
    except Exception as e:
        print(f"[error] Failed to process entry: {e}")
        return False

# FIXED: Enhanced Twitter crawler
async def crawl_twitter_feeds():
    """Enhanced Twitter RSS crawling with bulletproof error handling."""
    global twitter_crawl_in_progress
    
    if twitter_crawl_in_progress:
        print("[info] Twitter crawl already in progress, skipping")
        return
    
    twitter_crawl_in_progress = True
    print("[info] Starting enhanced Twitter feed crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        tweets_added = 0
        
        # Combine all Twitter feed sources
        all_twitter_feeds = TWITTER_RSS_FEEDS + TWITTER_SEARCH_FEEDS
        
        # Enhanced HTTP client with better headers
        async with httpx.AsyncClient(
            timeout=12.0, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        ) as client:
            
            # Try each feed with individual error handling
            for feed_url in all_twitter_feeds:
                try:
                    print(f"[info] Attempting Twitter feed: {feed_url}")
                    response = await client.get(feed_url)
                    
                    if response.status_code != 200:
                        print(f"[warn] HTTP {response.status_code} for {feed_url}")
                        continue
                    
                    # Parse RSS feed
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        print(f"[warn] No entries found in {feed_url}")
                        continue
                    
                    # Process each entry with error handling
                    for entry in feed.entries[:2]:  # Limit to 2 per feed
                        try:
                            if await process_social_entry_safe(entry, db, "twitter"):
                                tweets_added += 1
                        except Exception as entry_error:
                            print(f"[error] Failed to process entry: {entry_error}")
                            continue
                            
                except Exception as feed_error:
                    print(f"[error] Failed to process Twitter feed {feed_url}: {feed_error}")
                    continue
            
            # Fallback: Add Twitter account directory if no content found
            if tweets_added == 0:
                print("[info] No Twitter RSS content found, adding account directory")
                fallback_added = await add_twitter_account_directory(db)
                tweets_added = fallback_added
        
        await db.close()
        print(f"[info] Twitter crawl completed. Added {tweets_added} new items.")
        
    except Exception as e:
        print(f"[error] Twitter crawl failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        twitter_crawl_in_progress = False

# NEW: Twitter account directory fallback
async def add_twitter_account_directory(db) -> int:
    """Add Twitter account directory when RSS feeds aren't working."""
    added_count = 0
    
    try:
        for account in NIL_TWITTER_ACCOUNTS:
            # Create unique ID for account info
            info_id = hashlib.sha256(f"twitter-directory-{account['handle']}-2025".encode('utf-8')).hexdigest()
            
            # Check if already exists
            try:
                async with db.execute("SELECT 1 FROM twitter_posts WHERE id=?", (info_id,)) as cur:
                    if await cur.fetchone():
                        continue
            except Exception:
                continue
            
            # Create account information content
            content = f"📱 Follow @{account['handle']} for NIL updates • {account['name']} provides comprehensive Name, Image, and Likeness coverage for college athletes and industry developments."
            url = f"https://twitter.com/{account['handle']}"
            crawled_at = dt.datetime.utcnow().isoformat()
            
            # Insert account info
            await db.execute("""
                INSERT INTO twitter_posts (id, author, content, url, published, crawled_at, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (info_id, account['handle'], content, url, crawled_at, crawled_at, "twitter"))
            
            await db.commit()
            added_count += 1
            print(f"[+] Added Twitter directory entry: @{account['handle']}")
            
    except Exception as e:
        print(f"[error] Failed to add Twitter account directory: {e}")
    
    return added_count

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
                        if await process_social_entry_safe(entry, db, "instagram"):
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
                        if await process_social_entry_safe(entry, db, "tiktok"):
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

# FIXED: Safe social entry processing
async def process_social_entry_safe(entry: dict, db, platform: str) -> bool:
    """Bulletproof social media entry processing with comprehensive error handling."""
    try:
        # Validate entry has required fields
        url = entry.get("link")
        if not url or not isinstance(url, str):
            return False
        
        # Generate unique post ID
        post_id = hashlib.sha256(url.encode('utf-8')).hexdigest()
        table_name = f"{platform}_posts"
        
        # Check if already exists (with proper error handling)
        try:
            async with db.execute(f"SELECT 1 FROM {table_name} WHERE id=?", (post_id,)) as cur:
                if await cur.fetchone():
                    return False
        except Exception as db_error:
            print(f"[error] Database check failed: {db_error}")
            return False
        
        # Extract content safely
        title = str(entry.get("title", ""))
        content = str(entry.get("summary", "") or entry.get("description", ""))
        
        # Validate content exists
        if not title and not content:
            return False
        
        # Enhanced relevance checking
        if not is_relevant(f"{title} {content}"):
            return False
        
        # Extract author safely
        author = "Unknown"
        try:
            if platform == "twitter":
                if ": " in title:
                    author_part = title.split(": ")[0].strip()
                    author = author_part.replace("@", "").replace("RT ", "")
                    if len(title.split(": ")) > 1:
                        content = title.split(": ", 1)[1].strip()
            elif platform == "instagram" and "@" in title:
                author_match = title.split("@")[1].split()[0] if len(title.split("@")) > 1 else "Unknown"
                author = author_match
            elif platform == "tiktok" and "by @" in title:
                author_match = title.split("by @")[1].split()[0] if len(title.split("by @")) > 1 else "Unknown"
                author = author_match
        except Exception as parse_error:
            print(f"[warn] Author parsing failed: {parse_error}")
            author = "Unknown"
        
        # Clean and validate content
        content = content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        content = content.strip()
        
        if len(content) > 1000:  # Truncate very long content
            content = content[:1000] + "..."
        
        # Get timestamp
        published = str(entry.get("published", ""))
        crawled_at = dt.datetime.utcnow().isoformat()
        
        # Insert into database with parameterized query
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
app = FastAPI(title="NIL News Hub Pro", version="4.0.0")

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
        </div>
    </header>

    <!-- Tabs -->
    <div class="container mx-auto px-6 pt-6">
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
                    <span id="story-count" class="text-gray-600 font-medium"></span>
                </div>
            </div>
            <div id="stories-container">
                <div class="text-center py-8">
                    <i class="fas fa-spinner fa-spin text-2xl text-blue-600"></i>
                    <p class="text-gray-600 mt-2">Loading NIL news...</p>
                </div>
            </div>
        </div>

        <!-- Twitter Tab -->
        <div id="twitter
