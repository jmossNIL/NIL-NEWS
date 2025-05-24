#!/usr/bin/env python3
"""
Enhanced NIL News Aggregator with Twitter Integration - FIXED
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

# Twitter RSS feeds (using multiple nitter instances)
TWITTER_RSS_FEEDS = [
    f"https://nitter.net/{account['handle']}/rss" for account in NIL_TWITTER_ACCOUNTS[:5]
]

# Twitter search feeds
TWITTER_SEARCH_FEEDS = [
    "https://nitter.net/search/rss?q=NIL%20college",
    "https://nitter.net/search/rss?q=NIL%20deal",
]

DB_PATH = "/tmp/nil_news.db"

# Crawl flags
crawl_in_progress = False
twitter_crawl_in_progress = False

# Database setup
async def init_db():
    """Initialize database with safe schema."""
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
        
        await db.commit()
        await db.close()
        print("[info] Database initialized successfully")
        
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
                        if await process_twitter_entry(entry, db):
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

async def process_twitter_entry(entry: dict, db) -> bool:
    """Process a single Twitter entry."""
    try:
        url = entry.get("link")
        if not url:
            return False
        
        tweet_id = hashlib.sha256(url.encode()).hexdigest()
        async with db.execute("SELECT 1 FROM twitter_posts WHERE id=?", (tweet_id,)) as cur:
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
        
        published = entry.get("published", "")
        crawled_at = dt.datetime.utcnow().isoformat()
        
        await db.execute("""
            INSERT INTO twitter_posts (id, author, content, url, published, crawled_at, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tweet_id, author, content, url, published, crawled_at, "twitter"))
        
        await db.commit()
        print(f"[+] Stored tweet: @{author}: {content[:50]}...")
        return True
        
    except Exception as e:
        print(f"[error] Failed to process Twitter entry: {e}")
        return False

# FastAPI app
app = FastAPI(title="NIL News Hub Pro", version="3.0.0")

# Enhanced HTML template with tabs
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
    </style>
</head>
<body class="bg-gray-50">
    <!-- Header -->
    <header class="gradient-bg text-white py-8">
        <div class="container mx-auto px-6">
            <h1 class="text-4xl font-bold mb-2">
                <i class="fas fa-newspaper mr-3"></i>NIL News Hub Pro
            </h1>
            <p class="text-blue-100">Advanced NIL news aggregation with Twitter monitoring</p>
        </div>
    </header>

    <!-- Tabs -->
    <div class="container mx-auto px-6 pt-6">
        <div class="bg-white rounded-lg shadow-md mb-6">
            <div class="flex border-b">
                <button onclick="showTab('news')" id="news-tab" class="tab-active px-6 py-3 font-medium rounded-tl-lg">
                    <i class="fas fa-newspaper mr-2"></i>News Feed
                </button>
                <button onclick="showTab('twitter')" id="twitter-tab" class="px-6 py-3 font-medium hover:bg-gray-50 rounded-tr-lg">
                    <i class="fab fa-twitter mr-2"></i>Twitter Feed
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
    </div>

    <script>
        let allStories = [];
        let allTweets = [];
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
            }
        }

        async function loadStories() {
            try {
                console.log("Loading stories...");
                const response = await fetch('/api/summaries?limit=50');
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const stories = await response.json();
                console.log(`Loaded ${stories.length} stories`);
                
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
            
            let filteredStories = allStories.filter(story => {
                if (categoryFilter && story.category !== categoryFilter) return false;
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
                console.log("Loading Twitter posts...");
                const response = await fetch('/api/twitter?limit=30');
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const tweets = await response.json();
                console.log(`Loaded ${tweets.length} tweets`);
                
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
        
        async function refreshStories() {
            await loadStories();
        }

        async function refreshTwitter() {
            await loadTwitterPosts();
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
        
        console.log("Page loaded, starting to load data...");
        loadStories();
        
        setInterval(() => {
            if (currentTab === 'news') {
                loadStories();
            } else if (currentTab === 'twitter') {
                loadTwitterPosts();
            }
        }, 300000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Enhanced web dashboard with tabs."""
    return HTML_TEMPLATE

@app.get("/api/summaries")
async def get_summaries(limit: int = 50):
    """Get story summaries with bulletproof error handling."""
    print(f"[info] API request for {limit} summaries")
    
    try:
        if not os.path.exists(DB_PATH):
            print("[warn] Database doesn't exist yet")
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
            except Exception as e:
                print(f"[error] Error processing story row: {e}")
                continue
        
        print(f"[info] Returning {len(stories)} stories")
        return stories
        
    except Exception as e:
        print(f"[error] Database query failed: {e}")
        import traceback
        traceback.print_exc()
        return []

@app.get("/api/twitter")
async def get_twitter_posts(limit: int = 30):
    """Get Twitter posts with NIL content."""
    print(f"[info] API request for {limit} Twitter posts")
    
    try:
        if not os.path.exists(DB_PATH):
            print("[warn] Database doesn't exist yet")
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
                print(f"[error] Error processing tweet row: {e}")
                continue
        
        print(f"[info] Returning {len(tweets)} tweets")
        return tweets
        
    except Exception as e:
        print(f"[error] Twitter database query failed: {e}")
        import traceback
        traceback.print_exc()
        return []

@app.post("/api/crawl")
async def manual_crawl():
    """Trigger manual crawl."""
    try:
        asyncio.create_task(crawl_feeds())
        return {"status": "crawl started"}
    except Exception as e:
        print(f"[error] Failed to start crawl: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/crawl-twitter")
async def manual_twitter_crawl():
    """Trigger manual Twitter crawl."""
    try:
        asyncio.create_task(crawl_twitter_feeds())
        return {"status": "twitter crawl started"}
    except Exception as e:
        print(f"[error] Failed to start Twitter crawl: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/health")
async def health():
    """Health check."""
    try:
        if os.path.exists(DB_PATH):
            db = await aiosqlite.connect(DB_PATH)
            async with db.execute("SELECT COUNT(*) FROM stories") as cur:
                count = (await cur.fetchone())[0]
            await db.close()
            return {"status": "healthy", "stories": count, "version": "3.0.0"}
        else:
            return {"status": "healthy", "stories": 0, "version": "3.0.0"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Background crawling
async def background_crawler():
    """Enhanced background crawler."""
    # Do first crawl immediately
    if not crawl_in_progress:
        await crawl_feeds()
        await asyncio.sleep(30)
        if not twitter_crawl_in_progress:
            await crawl_twitter_feeds()
    
    while True:
        try:
            await asyncio.sleep(300)  # Wait 5 minutes
            if not crawl_in_progress:
                await crawl_feeds()
                await asyncio.sleep(30)
                if not twitter_crawl_in_progress:
                    await crawl_twitter_feeds()
        except Exception as e:
            print(f"[error] Background crawler failed: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    """Start enhanced background tasks."""
    try:
        await init_db()
        asyncio.create_task(background_crawler())
        print("[info] Application started successfully")
    except Exception as e:
        print(f"[error] Startup failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
