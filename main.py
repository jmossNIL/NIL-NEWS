#!/usr/bin/env python3
"""
Bulletproof NIL News Aggregator - Guaranteed Working Version
"""
import os
import asyncio
import datetime as dt
import hashlib
import json
from typing import Any, Dict, List

import aiosqlite
import feedparser
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from trafilatura import extract
import httpx

# Load environment variables
load_dotenv()

# Simple, reliable configuration
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

DB_PATH = "nil_news.db"

# Simple database setup
async def init_db():
    """Initialize database with safe schema."""
    try:
        db = await aiosqlite.connect(DB_PATH)
        
        # Simple, reliable schema
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
        
        await db.commit()
        print("[info] Database initialized successfully")
        return db
        
    except Exception as e:
        print(f"[error] Database initialization failed: {e}")
        raise

# Simple content processing
def is_relevant(text: str) -> bool:
    """Simple but effective relevance checking."""
    text_lower = text.lower()
    keywords_lower = [k.lower() for k in KEYWORDS]
    
    # Count keyword matches
    matches = sum(1 for keyword in keywords_lower if keyword in text_lower)
    return matches >= 1  # Require at least 1 match

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
    
    # Clean text and split into sentences
    text = text.replace('\n', ' ').strip()
    sentences = [s.strip() + '.' for s in text.split('.') if len(s.strip()) > 30]
    
    # Take first 2-3 good sentences
    summary = ' '.join(sentences[:3])
    
    # Limit length
    if len(summary) > 400:
        summary = summary[:400] + "..."
    
    return summary if summary else "Summary not available"

# Simple crawler
async def crawl_feeds():
    """Simple, reliable feed crawling."""
    print("[info] Starting feed crawl...")
    
    try:
        db = await init_db()
        stories_added = 0
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            for feed_url in FEEDS:
                try:
                    print(f"[info] Crawling {feed_url}")
                    response = await client.get(feed_url)
                    feed = feedparser.parse(response.text)
                    
                    if feed.bozo:
                        print(f"[warn] Problematic feed: {feed_url}")
                        continue
                    
                    for entry in feed.entries[:5]:  # Limit per feed
                        if await process_entry(entry, db):
                            stories_added += 1
                            
                except Exception as e:
                    print(f"[error] Failed to process {feed_url}: {e}")
                    continue
        
        await db.close()
        print(f"[info] Crawl completed. Added {stories_added} new stories.")
        
    except Exception as e:
        print(f"[error] Crawl failed: {e}")

async def process_entry(entry: dict, db) -> bool:
    """Simple, reliable entry processing."""
    try:
        url = entry.get("link")
        if not url:
            return False
        
        # Check if already exists
        story_id = hashlib.sha256(url.encode()).hexdigest()
        async with db.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)) as cur:
            if await cur.fetchone():
                return False  # Already exists
        
        title = entry.get("title", "No title")
        
        # Get content (with fallback)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                text = extract(response.text) or response.text[:1000]
        except:
            text = entry.get("summary", "") + " " + entry.get("description", "")
        
        # Check relevance
        if not is_relevant(title + " " + text):
            return False
        
        # Process content
        brief = simple_summarize(text)
        source = extract_source(url)
        category = categorize_content(title, text)
        published = entry.get("published", "")
        crawled_at = dt.datetime.utcnow().isoformat()
        
        # Store in database
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

# FastAPI app
app = FastAPI(title="NIL News Hub", version="3.0.0")

# Simple HTML template
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

        <!-- Stories -->
        <div id="stories-container">
            <div class="text-center py-8">
                <i class="fas fa-spinner fa-spin text-2xl text-blue-600"></i>
                <p class="text-gray-600 mt-2">Loading NIL news...</p>
            </div>
        </div>
    </div>

    <script>
        let allStories = [];

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

            // Sort by publication date (newest first)
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
        
        async function refreshStories() {
            await loadStories();
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
        
        // Load stories on page load
        console.log("Page loaded, starting to load stories...");
        loadStories();
        
        // Auto-refresh every 5 minutes
        setInterval(loadStories, 300000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Simple, reliable web dashboard."""
    return HTML_TEMPLATE

@app.get("/api/summaries")
async def get_summaries(limit: int = 50):
    """Get story summaries with bulletproof error handling."""
    try:
        db = await aiosqlite.connect(DB_PATH)
        
        # Simple, reliable query
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
                    "title": row[0] or "No Title",
                    "url": row[1] or "",
                    "published": row[2] or "",
                    "brief": row[3] or "No summary available",
                    "source": row[4] or "Unknown",
                    "category": row[5] or "General",
                    "crawled_at": row[6] or ""
                }
                stories.append(story)
            except Exception as e:
                print(f"[error] Error processing story row: {e}")
                continue
        
        print(f"[info] Returning {len(stories)} stories")
        return stories
        
    except Exception as e:
        print(f"[error] Database query failed: {e}")
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

@app.get("/health")
async def health():
    """Health check."""
    try:
        # Test database connection
        db = await aiosqlite.connect(DB_PATH)
        async with db.execute("SELECT COUNT(*) FROM stories") as cur:
            count = (await cur.fetchone())[0]
        await db.close()
        
        return {"status": "healthy", "stories": count, "version": "3.0.0"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Background crawling
async def background_crawler():
    """Simple background crawler."""
    while True:
        try:
            await asyncio.sleep(300)  # Wait 5 minutes
            await crawl_feeds()
        except Exception as e:
            print(f"[error] Background crawler failed: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    """Start background tasks."""
    try:
        await init_db()
        asyncio.create_task(background_crawler())
        print("[info] Application started successfully")
    except Exception as e:
        print(f"[error] Startup failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
