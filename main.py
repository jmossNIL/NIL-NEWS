#!/usr/bin/env python3
"""
Simplified NIL News Aggregator - Railway Compatible
"""
import os
import asyncio
import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, Dict, List
import sqlite3

import aiosqlite
import feedparser
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from trafilatura import extract
import httpx

# Load environment variables
load_dotenv()

# Configuration
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
    "https://www.burntorangenation.com/feed/",
    "https://www.goodbullhunting.com/feed/",
    "https://www.stateoftheu.com/feed/",
]

KEYWORDS = [
    "nil", "name image likeness", "nil deal", "nil collective",
    "collective", "booster", "endorsement", "sponsorship",
    "student-athlete", "college athlete", "transfer portal",
    "house v ncaa", "opendorse", "marketpryce",
]

DB_PATH = "nil_news.db"

# Database setup
async def init_db():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            published TEXT,
            summary TEXT,
            brief TEXT,
            crawled_at TEXT,
            source TEXT,
            category TEXT
        )
    """)
    await db.commit()
    return db

# Content processing
def is_relevant(text: str) -> bool:
    """Check if content is NIL-relevant."""
    text_lower = text.lower()
    keywords_lower = [k.lower() for k in KEYWORDS]
    return any(keyword in text_lower for keyword in keywords_lower)

def categorize_content(title: str, text: str) -> str:
    """Categorize content."""
    combined = (title + " " + text).lower()
    
    if any(word in combined for word in ["lawsuit", "settlement", "antitrust"]):
        return "Legal"
    elif any(word in combined for word in ["collective", "booster"]):
        return "Collectives"
    elif any(word in combined for word in ["marketplace", "platform"]):
        return "Technology"
    elif any(word in combined for word in ["social media", "influencer"]):
        return "Social Media"
    elif any(word in combined for word in ["transfer portal", "recruiting"]):
        return "Recruiting"
    else:
        return "General"

def extract_source(url: str) -> str:
    """Extract source name from URL."""
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

def summarize_text(text: str) -> str:
    """Create a summary of the text."""
    # Simple summarization - take first 2-3 sentences
    sentences = text.replace('\n', ' ').split('. ')
    good_sentences = [s.strip() + '.' for s in sentences[:3] if len(s.strip()) > 20]
    summary = ' '.join(good_sentences[:2])
    return summary[:400] + "..." if len(summary) > 400 else summary

# Crawler
async def crawl_feeds():
    """Crawl all RSS feeds."""
    db = await init_db()
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for feed_url in FEEDS:
            try:
                print(f"[info] Crawling {feed_url}")
                response = await client.get(feed_url)
                feed = feedparser.parse(response.text)
                
                if feed.bozo:
                    print(f"[warn] Bad feed: {feed_url}")
                    continue
                
                for entry in feed.entries[:5]:  # Limit per feed
                    await process_entry(entry, feed_url, db)
                    
            except Exception as e:
                print(f"[error] Failed to process {feed_url}: {e}")
    
    await db.close()
    print("[info] Crawl completed")

async def process_entry(entry: dict, feed_url: str, db):
    """Process a single feed entry."""
    url = entry.get("link")
    if not url:
        return
    
    # Check if already exists
    story_id = hashlib.sha256(url.encode()).hexdigest()
    async with db.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)) as cur:
        if await cur.fetchone():
            return
    
    title = entry.get("title", "No title")
    
    # Get content
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            text = extract(response.text) or response.text[:1000]
    except:
        text = entry.get("summary", "") + " " + entry.get("description", "")
    
    # Check relevance
    if not is_relevant(title + " " + text):
        return
    
    # Process content
    brief = summarize_text(text)
    source = extract_source(url)
    category = categorize_content(title, text)
    published = entry.get("published", "")
    crawled_at = dt.datetime.utcnow().isoformat()
    
    # Store in database
    await db.execute("""
        INSERT INTO stories VALUES (?,?,?,?,?,?,?,?,?)
    """, (story_id, title, url, published, text[:2000], brief, crawled_at, source, category))
    
    await db.commit()
    print(f"[+] Stored: {title[:50]}... [{source}]")

# FastAPI app
app = FastAPI(title="NIL News Aggregator", version="2.0.0")

# Modern HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIL News Hub</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .card-hover:hover { transform: translateY(-2px); transition: all 0.3s; }
    </style>
</head>
<body class="bg-gray-50">
    <!-- Header -->
    <header class="gradient-bg text-white py-8">
        <div class="container mx-auto px-6">
            <h1 class="text-4xl font-bold mb-2">
                <i class="fas fa-newspaper mr-3"></i>NIL News Hub
            </h1>
            <p class="text-blue-100">Real-time college sports NIL news aggregation</p>
        </div>
    </header>

    <!-- Controls -->
    <div class="container mx-auto px-6 py-6">
        <div class="bg-white rounded-lg shadow-md p-4 mb-6">
            <div class="flex gap-4 items-center">
                <button onclick="refreshStories()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">
                    <i class="fas fa-refresh mr-2"></i>Refresh Stories
                </button>
                <button onclick="crawlNow()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg">
                    <i class="fas fa-download mr-2"></i>Crawl Now
                </button>
                <span id="story-count" class="text-gray-600"></span>
            </div>
        </div>

        <!-- Stories -->
        <div id="stories-container">
            <div class="text-center py-8">
                <i class="fas fa-spinner fa-spin text-2xl text-blue-600"></i>
                <p class="text-gray-600 mt-2">Loading stories...</p>
            </div>
        </div>
    </div>

    <script>
        async function loadStories() {
            try {
                const response = await fetch('/api/summaries?limit=50');
                const stories = await response.json();
                
                document.getElementById('story-count').textContent = `${stories.length} stories loaded`;
                
                const container = document.getElementById('stories-container');
                
                if (stories.length === 0) {
                    container.innerHTML = `
                        <div class="text-center py-8">
                            <p class="text-gray-600">No stories yet. Click "Crawl Now" to fetch the latest NIL news!</p>
                        </div>
                    `;
                    return;
                }
                
                container.innerHTML = stories.map(story => `
                    <article class="bg-white rounded-lg shadow-md hover:shadow-lg card-hover p-6 mb-6">
                        <div class="flex items-start justify-between mb-4">
                            <div class="flex gap-2">
                                <span class="bg-blue-500 text-white text-xs px-2 py-1 rounded-full">
                                    ${story.category || 'General'}
                                </span>
                                <span class="bg-green-500 text-white text-xs px-2 py-1 rounded-full">
                                    ${story.source || 'Unknown'}
                                </span>
                            </div>
                            <time class="text-sm text-gray-500">
                                ${formatDate(story.published || story.crawled_at)}
                            </time>
                        </div>
                        
                        <h2 class="text-xl font-bold text-gray-900 mb-3">
                            <a href="${story.url}" target="_blank" class="hover:text-blue-600">
                                ${story.title}
                            </a>
                        </h2>
                        
                        <p class="text-gray-700 mb-4">${story.brief}</p>
                        
                        <a href="${story.url}" target="_blank" 
                           class="inline-flex items-center text-blue-600 hover:text-blue-800 font-medium">
                            Read Full Article
                            <i class="fas fa-external-link-alt ml-2 text-sm"></i>
                        </a>
                    </article>
                `).join('');
                
            } catch (error) {
                console.error('Error loading stories:', error);
                document.getElementById('stories-container').innerHTML = 
                    '<div class="text-center text-red-500 py-8">Error loading stories</div>';
            }
        }
        
        async function refreshStories() {
            await loadStories();
        }
        
        async function crawlNow() {
            try {
                const response = await fetch('/api/crawl', { method: 'POST' });
                if (response.ok) {
                    alert('Crawl started! Refresh in 1-2 minutes to see new stories.');
                }
            } catch (error) {
                alert('Error starting crawl');
            }
        }
        
        function formatDate(dateString) {
            if (!dateString) return 'Unknown';
            const date = new Date(dateString);
            const now = new Date();
            const diff = now - date;
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const days = Math.floor(hours / 24);
            
            if (hours < 24) return `${hours}h ago`;
            if (days < 7) return `${days}d ago`;
            return date.toLocaleDateString();
        }
        
        // Load stories on page load
        loadStories();
        
        // Auto-refresh every 5 minutes
        setInterval(loadStories, 300000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Web dashboard."""
    return HTML_TEMPLATE

@app.get("/api/summaries")
async def get_summaries(limit: int = 50):
    """Get story summaries."""
    db = await aiosqlite.connect(DB_PATH)
    
    async with db.execute("""
        SELECT title, url, published, brief, source, category, crawled_at
        FROM stories
        ORDER BY datetime(COALESCE(published, crawled_at)) DESC
        LIMIT ?
    """, (limit,)) as cur:
        rows = await cur.fetchall()
    
    await db.close()
    
    return [
        {
            "title": row[0],
            "url": row[1], 
            "published": row[2],
            "brief": row[3],
            "source": row[4],
            "category": row[5],
            "crawled_at": row[6]
        }
        for row in rows
    ]

@app.post("/api/crawl")
async def manual_crawl():
    """Trigger manual crawl."""
    asyncio.create_task(crawl_feeds())
    return {"status": "crawl started"}

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy"}

# Background crawling
async def background_crawler():
    """Background task for crawling."""
    while True:
        try:
            await crawl_feeds()
            await asyncio.sleep(300)  # 5 minutes
        except Exception as e:
            print(f"[error] Background crawler failed: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    """Start background tasks."""
    await init_db()
    asyncio.create_task(background_crawler())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
