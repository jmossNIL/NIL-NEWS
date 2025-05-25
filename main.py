#!/usr/bin/env python3
"""
Enhanced NIL News Aggregator with Instagram, TikTok & Twitter Integration - COMPLETE FIXED
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
]

# TikTok accounts to monitor
NIL_TIKTOK_ACCOUNTS = [
    {"handle": "livvydunne", "name": "Livvy Dunne"},
    {"handle": "cavindertwins", "name": "Cavinder Twins"},
    {"handle": "shedeursanders", "name": "Shedeur Sanders"},
    {"handle": "lsu.gymgirl", "name": "LSU Gymnast"},
    {"handle": "opendorse", "name": "Opendorse"},
    {"handle": "marketpryce", "name": "MarketPryce"},
]

# FIXED: Working Nitter instances
WORKING_NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net", 
    "https://nitter.woodland.cafe"
]

# FIXED: Generate Twitter RSS feeds using working instances
TWITTER_RSS_FEEDS = []
for instance in WORKING_NITTER_INSTANCES[:2]:
    for account in NIL_TWITTER_ACCOUNTS[:3]:
        TWITTER_RSS_FEEDS.append(f"{instance}/{account['handle']}/rss")

# FIXED: Instagram feeds using Google News (more reliable)
INSTAGRAM_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=%22Instagram%22+%22NIL%22+%22college+athlete%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22Livvy+Dunne%22+%22Instagram%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22Cavinder+twins%22+%22Instagram%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22college+athlete%22+%22Instagram+followers%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22NIL+deal%22+%22social+media%22&hl=en-US&gl=US&ceid=US:en",
]

# FIXED: TikTok feeds using Google News (more reliable)
TIKTOK_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=%22TikTok%22+%22NIL%22+%22college+athlete%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22Livvy+Dunne%22+%22TikTok%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22college+athlete%22+%22TikTok+viral%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22TikTok+influencer%22+%22college+sports%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22social+media%22+%22college+athlete%22+%22endorsement%22&hl=en-US&gl=US&ceid=US:en",
]

# FIXED: Enhanced Twitter search using Google News
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
        print("[info] Database initialized successfully")
        
    except Exception as e:
        print(f"[error] Database initialization failed: {e}")
        raise

# Content processing functions
def is_relevant(text: str) -> bool:
    """Enhanced relevance checking."""
    text_lower = text.lower()
    keywords_lower = [k.lower() for k in KEYWORDS]
    nil_keywords = ["nil", "name image likeness", "collective", "endorsement", 
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

# Main news crawler
async def crawl_feeds():
    """Simple, reliable feed crawling."""
    global crawl_in_progress
    
    if crawl_in_progress:
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
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        continue
                        
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        continue
                    
                    for entry in feed.entries[:5]:
                        if await process_entry(entry, db):
                            stories_added += 1
                            
                except Exception as e:
                    continue
        
        await db.close()
        print(f"[info] Crawl completed. Added {stories_added} new stories.")
        
    except Exception as e:
        print(f"[error] Crawl failed: {e}")
    finally:
        crawl_in_progress = False

async def process_entry(entry: dict, db) -> bool:
    """Simple entry processing."""
    try:
        url = entry.get("link")
        if not url:
            return False
        
        story_id = hashlib.sha256(url.encode()).hexdigest()
        async with db.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)) as cur:
            if await cur.fetchone():
                return False
        
        title = entry.get("title", "No title")
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
        print(f"[+] Stored: {title[:50]}...")
        return True
        
    except Exception as e:
        return False

# FIXED: Enhanced Twitter crawler
async def crawl_twitter_feeds():
    """Enhanced Twitter RSS crawling."""
    global twitter_crawl_in_progress
    
    if twitter_crawl_in_progress:
        return
    
    twitter_crawl_in_progress = True
    print("[info] Starting Twitter crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        tweets_added = 0
        
        all_twitter_feeds = TWITTER_RSS_FEEDS + TWITTER_SEARCH_FEEDS
        
        async with httpx.AsyncClient(timeout=12.0, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}) as client:
            for feed_url in all_twitter_feeds:
                try:
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        continue
                    
                    feed = feedparser.parse(response.text)
                    if not hasattr(feed, 'entries') or not feed.entries:
                        continue
                    
                    for entry in feed.entries[:2]:
                        if await process_social_entry(entry, db, "twitter"):
                            tweets_added += 1
                            
                except Exception as e:
                    continue
            
            if tweets_added == 0:
                fallback_added = await add_twitter_account_directory(db)
                tweets_added = fallback_added
        
        await db.close()
        print(f"[info] Twitter crawl completed. Added {tweets_added} items.")
        
    except Exception as e:
        print(f"[error] Twitter crawl failed: {e}")
    finally:
        twitter_crawl_in_progress = False

async def add_twitter_account_directory(db) -> int:
    """Add Twitter account directory."""
    added_count = 0
    
    try:
        for account in NIL_TWITTER_ACCOUNTS:
            info_id = hashlib.sha256(f"twitter-directory-{account['handle']}-2025".encode('utf-8')).hexdigest()
            
            async with db.execute("SELECT 1 FROM twitter_posts WHERE id=?", (info_id,)) as cur:
                if await cur.fetchone():
                    continue
            
            content = f"📱 Follow @{account['handle']} for NIL updates • {account['name']} provides comprehensive Name, Image, and Likeness coverage."
            url = f"https://twitter.com/{account['handle']}"
            crawled_at = dt.datetime.utcnow().isoformat()
            
            await db.execute("""
                INSERT INTO twitter_posts (id, author, content, url, published, crawled_at, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (info_id, account['handle'], content, url, crawled_at, crawled_at, "twitter"))
            
            await db.commit()
            added_count += 1
            
    except Exception as e:
        print(f"[error] Failed to add Twitter directory: {e}")
    
    return added_count

# FIXED: Enhanced Instagram crawler using news coverage
async def crawl_instagram_feeds():
    """Enhanced Instagram crawling using news coverage."""
    global instagram_crawl_in_progress
    
    if instagram_crawl_in_progress:
        return
    
    instagram_crawl_in_progress = True
    print("[info] Starting Instagram news crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        posts_added = 0
        
        async with httpx.AsyncClient(
            timeout=12.0, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
        ) as client:
            
            for feed_url in INSTAGRAM_RSS_FEEDS:
                try:
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        continue
                        
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        continue
                    
                    for entry in feed.entries[:3]:
                        try:
                            if await process_social_news_entry(entry, db, "instagram"):
                                posts_added += 1
                        except Exception:
                            continue
                            
                except Exception:
                    continue
        
        if posts_added == 0:
            fallback_added = await add_instagram_account_directory(db)
            posts_added = fallback_added
        
        await db.close()
        print(f"[info] Instagram crawl completed. Added {posts_added} items.")
        
    except Exception as e:
        print(f"[error] Instagram crawl failed: {e}")
    finally:
        instagram_crawl_in_progress = False

# FIXED: Enhanced TikTok crawler using news coverage
async def crawl_tiktok_feeds():
    """Enhanced TikTok crawling using news coverage."""
    global tiktok_crawl_in_progress
    
    if tiktok_crawl_in_progress:
        return
    
    tiktok_crawl_in_progress = True
    print("[info] Starting TikTok news crawl...")
    
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        posts_added = 0
        
        async with httpx.AsyncClient(
            timeout=12.0, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
        ) as client:
            
            for feed_url in TIKTOK_RSS_FEEDS:
                try:
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        continue
                        
                    feed = feedparser.parse(response.text)
                    
                    if not hasattr(feed, 'entries') or not feed.entries:
                        continue
                    
                    for entry in feed.entries[:3]:
                        try:
                            if await process_social_news_entry(entry, db, "tiktok"):
                                posts_added += 1
                        except Exception:
                            continue
                            
                except Exception:
                    continue
        
        if posts_added == 0:
            fallback_added = await add_tiktok_account_directory(db)
            posts_added = fallback_added
        
        await db.close()
        print(f"[info] TikTok crawl completed. Added {posts_added} items.")
        
    except Exception as e:
        print(f"[error] TikTok crawl failed: {e}")
    finally:
        tiktok_crawl_in_progress = False

# NEW: Process social media news entries
async def process_social_news_entry(entry: dict, db, platform: str) -> bool:
    """Process news articles about social media platforms."""
    try:
        url = entry.get("link")
        if not url or not isinstance(url, str):
            return False
        
        post_id = hashlib.sha256(url.encode('utf-8')).hexdigest()
        table_name = f"{platform}_posts"
        
        async with db.execute(f"SELECT 1 FROM {table_name} WHERE id=?", (post_id,)) as cur:
            if await cur.fetchone():
                return False
        
        title = str(entry.get("title", ""))
        description = str(entry.get("summary", "") or entry.get("description", ""))
        
        full_text = f"{title} {description}".lower()
        
        # Enhanced relevance checking for social media news
        platform_keywords = {
            "instagram": ["instagram", "ig", "social media", "followers", "posts", "content creator"],
            "tiktok": ["tiktok", "viral", "video", "social media", "content creator", "influencer"]
        }
        
        nil_keywords = ["nil", "name image likeness", "college athlete", "student athlete", 
                       "endorsement", "sponsorship", "collective", "ncaa"]
        
        has_platform = any(keyword in full_text for keyword in platform_keywords[platform])
        has_nil = any(keyword in full_text for keyword in nil_keywords)
        
        if not (has_platform and has_nil):
            return False
        
        source = entry.get("source", {})
        if isinstance(source, dict):
            author = source.get("title", "News Source")
        else:
            author = str(source) if source else "News Source"
        
        content = f"📰 {title}"
        if description and len(description) > 50:
            content += f" • {description[:200]}..."
        
        content = content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
        
        published = str(entry.get("published", ""))
        crawled_at = dt.datetime.utcnow().isoformat()
        
        await db.execute(f"""
            INSERT INTO {table_name} (id, author, content, url, published, crawled_at, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (post_id, author, content, url, published, crawled_at, f"{platform}_news"))
        
        await db.commit()
        print(f"[+] Stored {platform} news: {title[:50]}...")
        return True
        
    except Exception as e:
        return False

# Instagram account directory fallback
async def add_instagram_account_directory(db) -> int:
    """Add Instagram account directory."""
    added_count = 0
    
    try:
        for account in NIL_INSTAGRAM_ACCOUNTS:
            info_id = hashlib.sha256(f"instagram-directory-{account['handle']}-2025".encode('utf-8')).hexdigest()
            
            async with db.execute("SELECT 1 FROM instagram_posts WHERE id=?", (info_id,)) as cur:
                if await cur.fetchone():
                    continue
            
            content = f"📸 Follow @{account['handle']} on Instagram • {account['name']} shares NIL content, lifestyle, and behind-the-scenes college athlete experiences."
            url = f"https://instagram.com/{account['handle']}"
            crawled_at = dt.datetime.utcnow().isoformat()
            
            await db.execute("""
                INSERT INTO instagram_posts (id, author, content, url, published, crawled_at, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (info_id, account['handle'], content, url, crawled_at, crawled_at, "instagram"))
            
            await db.commit()
            added_count += 1
            
    except Exception as e:
        print(f"[error] Failed to add Instagram directory: {e}")
    
    return added_count

# TikTok account directory fallback
async def add_tiktok_account_directory(db) -> int:
    """Add TikTok account directory."""
    added_count = 0
    
    try:
        for account in NIL_TIKTOK_ACCOUNTS:
            info_id = hashlib.sha256(f"tiktok-directory-{account['handle']}-2025".encode('utf-8')).hexdigest()
            
            async with db.execute("SELECT 1 FROM tiktok_posts WHERE id=?", (info_id,)) as cur:
                if await cur.fetchone():
                    continue
            
            content = f"🎵 Follow @{account['handle']} on TikTok • {account['name']} creates viral content, NIL partnerships, and gives fans a look into college athlete life."
            url = f"https://tiktok.com/@{account['handle']}"
            crawled_at = dt.datetime.utcnow().isoformat()
            
            await db.execute("""
                INSERT INTO tiktok_posts (id, author, content, url, published, crawled_at, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (info_id, account['handle'], content, url, crawled_at, crawled_at, "tiktok"))
            
            await db.commit()
            added_count += 1
            
    except Exception as e:
        print(f"[error] Failed to add TikTok directory: {e}")
    
    return added_count

# Legacy social entry processing (for Twitter)
async def process_social_entry(entry: dict, db, platform: str) -> bool:
    """Process social media entry (Twitter)."""
    try:
        url = entry.get("link")
        if not url or not isinstance(url, str):
            return False
        
        post_id = hashlib.sha256(url.encode('utf-8')).hexdigest()
        table_name = f"{platform}_posts"
        
        async with db.execute(f"SELECT 1 FROM {table_name} WHERE id=?", (post_id,)) as cur:
            if await cur.fetchone():
                return False
        
        title = str(entry.get("title", ""))
        content = str(entry.get("summary", "") or entry.get("description", ""))
        
        if not title and not content:
            return False
        
        if not is_relevant(f"{title} {content}"):
            return False
        
        author = "Unknown"
        if platform == "twitter" and ": " in title:
            author_part = title.split(": ")[0].strip()
            author = author_part.replace("@", "").replace("RT ", "")
            content = title.split(": ", 1)[1].strip() if len(title.split(": ")) > 1 else content
        
        content = content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
        
        if len(content) > 1000:
            content = content[:1000] + "..."
        
        published = str(entry.get("published", ""))
        crawled_at = dt.datetime.utcnow().isoformat()
        
        await db.execute(f"""
            INSERT INTO {table_name} (id, author, content, url, published, crawled_at, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (post_id, author, content, url, published, crawled_at, platform))
        
        await db.commit()
        print(f"[+] Stored {platform}: @{author}")
        return True
        
    except Exception as e:
        return False

# FastAPI app
app = FastAPI(title="NIL News Hub Pro", version="4.0.0")

# Complete HTML template
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
    <header class="gradient-bg text-white py-8">
        <div class="container mx-auto px-6">
            <h1 class="text-4xl font-bold mb-2">
                <i class="fas fa-newspaper mr-3"></i>NIL News Hub Pro
            </h1>
            <p class="text-blue-100">Complete NIL monitoring across all platforms</p>
        </div>
    </header>

    <div class="container mx-auto px-6 pt-6">
        <div class="bg-white rounded-lg shadow-md mb-6">
            <div class="flex border-b overflow-x-auto">
                <button onclick="showTab('news')" id="news-tab" class="tab-active px-6 py-3 font-medium rounded-tl-lg flex-shrink-0">
                    <i class="fas fa-newspaper mr-2"></i>News
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

        <div id="news-content" class="tab-content">
            <div class="bg-white rounded-lg shadow-md p-4 mb-6">
                <div class="flex gap-4 items-center flex-wrap">
                    <button onclick="refreshStories()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-refresh mr-2"></i>Refresh
                    </button>
                    <button onclick="crawlNow()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-download mr-2"></i>Crawl Now
                    </button>
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

        async function loadStories() {
            try {
                const response = await fetch('/api/summaries?limit=50');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const stories = await response.json();
                allStories = stories;
                document.getElementById('story-count').textContent = `${stories.length} stories loaded`;
                renderStories();
                
            } catch (error) {
                document.getElementById('stories-container').innerHTML = 
                    `<div class="text-center text-red-500 py-8">
                        <p>Error loading stories: ${error.message}</p>
                        <button onclick="refreshStories()" class="mt-4 bg-blue-600 text-white px-4 py-2 rounded">
                            Try Again
                        </button>
                    </div>`;
            }
        }

        function renderStories() {
            const container = document.getElementById('stories-container');
            
            if (allStories.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <i class="fas fa-newspaper text-4xl text-gray-400 mb-4"></i>
                        <p class="text-gray-600 text-lg">No stories found.</p>
                        <button onclick="crawlNow()" class="mt-4 bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded-lg">
                            <i class="fas fa-download mr-2"></i>Get Stories
                        </button>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = allStories.map(story => `
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
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const tweets = await response.json();
                allTweets = tweets;
                document.getElementById('twitter-count').textContent = `${tweets.length} tweets loaded`;
                renderTwitterPosts();
                
            } catch (error) {
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
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const posts = await response.json();
                allInstagramPosts = posts;
                document.getElementById('instagram-count').textContent = `${posts.length} posts loaded`;
                renderInstagramPosts();
                
            } catch (error) {
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
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const posts = await response.json();
                allTikTokPosts = posts;
                document.getElementById('tiktok-count').textContent = `${posts.length} videos loaded`;
                renderTikTokPosts();
                
            } catch (error) {
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
        
        loadStories();
        
        setInterval(() => {
            if (currentTab === 'news') {
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
async def get_summaries(limit: int = 50):
    """Get story summaries."""
    try:
        if not os.path.exists(DB_PATH):
            return []
        
        db = await aiosqlite.connect(DB_PATH)
        
        async with db.execute("""
            SELECT title, url, published, brief, source, category, crawled_at
            FROM stories
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
        
        stories = []
        for row in rows:
            try:
                story = {
                    "title": str(row[0] or "No Title"),
                    "url": str(row[1] or ""),
                    "published": str(row[2] or ""),
                    "brief": str(row[3] or "No summary available"),
                    "source": str(row[4] or "Unknown"),
                    "category": str(row[5] or "General"),
                    "crawled_at": str(row[6] or "")
                }
                stories.append(story)
            except Exception:
                continue
        
        return stories
        
    except Exception as e:
        print(f"[error] Database query failed: {e}")
        return []

@app.get("/api/twitter")
async def get_twitter_posts(limit: int = 30):
    """Get Twitter posts."""
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
            except Exception:
                continue
        
        return tweets
        
    except Exception as e:
        print(f"[error] Twitter database query failed: {e}")
        return []

@app.get("/api/instagram")
async def get_instagram_posts(limit: int = 30):
    """Get Instagram posts."""
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
            except Exception:
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
                "version": "4.0.0"
            }
        else:
            return {"status": "healthy", "stories": 0, "version": "4.0.0"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Enhanced background crawling
async def background_crawler():
    """Enhanced background crawler for all platforms."""
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
        print("[info] NIL News Hub Pro started successfully")
    except Exception as e:
        print(f"[error] Startup failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
                    "url": str(row[2] or ""),
                    "published": str(row[3] or ""),
                    "crawled_at": str(row[4] or "")
                }
                posts.append(post)
            except Exception:
                continue
        
        return posts
        
    except Exception as e:
        print(f"[error] Instagram database query failed: {e}")
        return []

@app.get("/api/tiktok")
async def get_tiktok_posts(limit: int = 30):
    """Get TikTok posts."""
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
