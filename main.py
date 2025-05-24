#!/usr/bin/env python3
"""
Minimal Working NIL News Aggregator - Guaranteed to work
"""
import os
import asyncio
import datetime
import hashlib
from typing import List, Dict, Any

import aiosqlite
import feedparser
import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from trafilatura import extract

# Simple configuration
FEEDS = [
    "https://frontofficesports.com/feed/",
    "https://businessofcollegesports.com/feed/",
    "https://www.espn.com/college-sports/rss",
    "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
]

KEYWORDS = ["nil", "name image likeness", "collective", "booster", "endorsement", "college athlete"]
DB_PATH = "/tmp/nil_news.db"

# Database
async def init_db():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            brief TEXT,
            source TEXT,
            crawled_at TEXT
        )
    """)
    await db.commit()
    await db.close()

def is_relevant(text: str) -> bool:
    return any(keyword in text.lower() for keyword in KEYWORDS)

def get_source(url: str) -> str:
    if "frontofficesports.com" in url:
        return "Front Office Sports"
    elif "businessofcollegesports.com" in url:
        return "Business of College Sports"
    elif "espn.com" in url:
        return "ESPN"
    elif "news.google.com" in url:
        return "Google News"
    else:
        return "Unknown"

# Crawler
async def crawl_feeds():
    try:
        await init_db()
        db = await aiosqlite.connect(DB_PATH)
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for feed_url in FEEDS:
                try:
                    print(f"Crawling {feed_url}")
                    response = await client.get(feed_url)
                    feed = feedparser.parse(response.text)
                    
                    for entry in feed.entries[:3]:
                        url = entry.get("link", "")
                        title = entry.get("title", "")
                        
                        if not url or not title:
                            continue
                            
                        if not is_relevant(title):
                            continue
                            
                        story_id = hashlib.sha256(url.encode()).hexdigest()
                        
                        # Check if exists
                        async with db.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)) as cur:
                            if await cur.fetchone():
                                continue
                        
                        source = get_source(url)
                        brief = title  # Simple: use title as brief
                        crawled_at = datetime.datetime.utcnow().isoformat()
                        
                        await db.execute("""
                            INSERT INTO stories (id, title, url, brief, source, crawled_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (story_id, title, url, brief, source, crawled_at))
                        await db.commit()
                        print(f"Stored: {title[:50]}")
                        
                except Exception as e:
                    print(f"Error with feed {feed_url}: {e}")
                    continue
        
        await db.close()
        print("Crawl completed")
        
    except Exception as e:
        print(f"Crawl error: {e}")

# FastAPI app
app = FastAPI()

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>NIL News</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-6">NIL News Hub</h1>
        
        <div class="mb-4">
            <button onclick="refresh()" class="bg-blue-500 text-white px-4 py-2 rounded mr-2">
                Refresh
            </button>
            <button onclick="crawl()" class="bg-green-500 text-white px-4 py-2 rounded">
                Crawl Now
            </button>
        </div>
        
        <div id="stories">Loading...</div>
    </div>

    <script>
        async function loadStories() {
            try {
                const response = await fetch('/api/stories');
                const stories = await response.json();
                
                const container = document.getElementById('stories');
                
                if (stories.length === 0) {
                    container.innerHTML = '<p>No stories yet. Click "Crawl Now" to fetch news!</p>';
                    return;
                }
                
                container.innerHTML = stories.map(story => `
                    <div class="bg-white p-4 mb-4 rounded shadow">
                        <h3 class="font-bold mb-2">
                            <a href="${story.url}" target="_blank" class="text-blue-600 hover:underline">
                                ${story.title}
                            </a>
                        </h3>
                        <p class="text-gray-600 text-sm">
                            Source: ${story.source} | ${new Date(story.crawled_at).toLocaleDateString()}
                        </p>
                    </div>
                `).join('');
                
            } catch (error) {
                document.getElementById('stories').innerHTML = 'Error loading stories';
            }
        }
        
        async function refresh() {
            await loadStories();
        }
        
        async function crawl() {
            try {
                await fetch('/api/crawl', { method: 'POST' });
                alert('Crawl started! Refresh in 1 minute.');
            } catch (error) {
                alert('Error starting crawl');
            }
        }
        
        loadStories();
        setInterval(loadStories, 60000);
    </script>
</body>
</html>
"""

@app.get("/")
async def root():
    return HTMLResponse(HTML)

@app.get("/api/stories")
async def get_stories():
    try:
        if not os.path.exists(DB_PATH):
            return []
            
        db = await aiosqlite.connect(DB_PATH)
        async with db.execute("SELECT title, url, source, crawled_at FROM stories ORDER BY crawled_at DESC LIMIT 20") as cur:
            rows = await cur.fetchall()
        await db.close()
        
        return [{"title": r[0], "url": r[1], "source": r[2], "crawled_at": r[3]} for r in rows]
    except Exception as e:
        print(f"API error: {e}")
        return []

@app.post("/api/crawl")
async def manual_crawl():
    asyncio.create_task(crawl_feeds())
    return {"status": "started"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# Background crawler
async def background_crawler():
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            await crawl_feeds()
        except Exception as e:
            print(f"Background error: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    try:
        await init_db()
        asyncio.create_task(background_crawler())
        # Do initial crawl
        asyncio.create_task(crawl_feeds())
    except Exception as e:
        print(f"Startup error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
