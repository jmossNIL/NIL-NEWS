#!/usr/bin/env python3
"""
Modern NIL News Aggregator - Optimized for Railway/Vercel deployment
"""
import os
import asyncio
import asyncpg
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import feedparser
from datetime import datetime, timedelta
import hashlib
import yaml
from typing import List, Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment-based configuration
class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/nilnews")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    CRAWL_INTERVAL = int(os.getenv("CRAWL_INTERVAL_MINUTES", "5"))
    
    # Enhanced feed list (verified working)
    FEEDS = [
        "https://frontofficesports.com/feed/",
        "https://sportico.com/feed/",
        "https://businessofcollegesports.com/feed/",
        "https://www.espn.com/college-sports/rss",
        "https://sports.yahoo.com/college/rss",
        "https://www.si.com/college/.rss",
        "https://www.adweek.com/feed/",
        "https://marketingland.com/feed",
        "https://news.google.com/rss/search?q=NIL+college+athlete&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NIL+collective+booster&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=college+sports+transfer+portal&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=NCAA+antitrust+lawsuit&hl=en-US&gl=US&ceid=US:en",
        # SB Nation team feeds
        "https://www.burntorangenation.com/feed/",
        "https://www.goodbullhunting.com/feed/",
        "https://www.stateoftheu.com/feed/",
        "https://www.addictedtoquack.com/feed/",
        "https://www.andthevalleyshook.com/feed/",
        "https://www.dawgsports.com/feed/",
        "https://www.rollbamaroll.com/feed/",
    ]
    
    KEYWORDS = [
        "nil", "name image likeness", "nil deal", "nil collective", "nil marketplace",
        "collective", "booster", "endorsement", "sponsorship", "brand deal",
        "student-athlete", "college athlete", "transfer portal", "recruiting",
        "house v ncaa", "house settlement", "opendorse", "marketpryce",
        "social media influencer", "athlete influencer", "nil influencer",
        "ncaa", "compliance", "eligibility", "fair market value",
    ]

config = Config()

# Database setup
async def init_database():
    """Initialize PostgreSQL database with proper schema."""
    conn = await asyncpg.connect(config.DATABASE_URL)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            published TIMESTAMP WITH TIME ZONE,
            summary TEXT,
            brief TEXT,
            crawled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            source TEXT,
            category TEXT,
            relevance_score FLOAT DEFAULT 0.0
        );
        
        CREATE INDEX IF NOT EXISTS idx_stories_published ON stories(published DESC);
        CREATE INDEX IF NOT EXISTS idx_stories_crawled ON stories(crawled_at DESC);
        CREATE INDEX IF NOT EXISTS idx_stories_category ON stories(category);
        CREATE INDEX IF NOT EXISTS idx_stories_source ON stories(source);
    """)
    
    await conn.close()

# Content processing
class ContentProcessor:
    def __init__(self):
        self.keywords = [k.lower() for k in config.KEYWORDS]
        self.client = httpx.AsyncClient(timeout=15.0)
    
    def calculate_relevance(self, title: str, content: str) -> float:
        """Calculate relevance score based on keyword density and importance."""
        text = (title + " " + content).lower()
        
        # High-value keywords (worth more points)
        high_value = ["nil deal", "nil collective", "house v ncaa", "nil endorsement"]
        medium_value = ["nil", "collective", "booster", "endorsement"]
        
        score = 0.0
        for keyword in high_value:
            if keyword in text:
                score += 3.0
        
        for keyword in medium_value:
            if keyword in text:
                score += 1.0
        
        return min(score, 10.0)  # Cap at 10
    
    def categorize_content(self, title: str, content: str) -> str:
        """Smart content categorization."""
        text = (title + " " + content).lower()
        
        categories = {
            "Legal": ["lawsuit", "settlement", "antitrust", "legal", "court", "house v ncaa"],
            "Collectives": ["collective", "booster", "donor", "fund"],
            "Technology": ["marketplace", "platform", "app", "technology", "opendorse"],
            "Social Media": ["social media", "influencer", "instagram", "tiktok", "youtube"],
            "Recruiting": ["transfer portal", "recruiting", "prospect", "commit"],
            "High School": ["high school", "prep", "youth"],
            "Business": ["revenue", "deal", "contract", "partnership", "sponsorship"],
        }
        
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category
        
        return "General"
    
    def extract_source(self, url: str) -> str:
        """Extract clean source name from URL."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        
        source_map = {
            "frontofficesports.com": "Front Office Sports",
            "sportico.com": "Sportico",
            "businessofcollegesports.com": "Business of College Sports",
            "espn.com": "ESPN",
            "si.com": "Sports Illustrated",
            "yahoo.com": "Yahoo Sports",
            "burntorangenation.com": "Burnt Orange Nation",
            "goodbullhunting.com": "Good Bull Hunting",
            "stateoftheu.com": "State of the U",
            "news.google.com": "Google News",
        }
        
        for key, value in source_map.items():
            if key in domain:
                return value
        
        return domain.replace("www.", "").replace(".com", "").title()

# FastAPI app
app = FastAPI(
    title="NIL News Aggregator",
    description="Modern NIL news aggregation platform",
    version="3.0.0"
)

# CORS middleware for web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize processor
processor = ContentProcessor()

# Modern web interface
MODERN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIL News Hub</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        [x-cloak] { display: none !important; }
        .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .glass { background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); }
    </style>
</head>
<body class="bg-gray-50">
    <div x-data="nilDashboard()" x-init="loadStories()" class="min-h-screen">
        <!-- Header -->
        <header class="gradient-bg text-white">
            <div class="container mx-auto px-6 py-8">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-4xl font-bold mb-2">
                            <i class="fas fa-newspaper mr-3"></i>NIL News Hub
                        </h1>
                        <p class="text-blue-100">Real-time college sports NIL news</p>
                    </div>
                    <div class="glass rounded-lg p-4">
                        <div class="text-right">
                            <div class="text-2xl font-bold" x-text="stories.length"></div>
                            <div class="text-sm opacity-75">Stories Loaded</div>
                        </div>
                    </div>
                </div>
            </div>
        </header>

        <!-- Filters -->
        <div class="container mx-auto px-6 py-6">
            <div class="bg-white rounded-lg shadow-lg p-6 mb-6">
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Category</label>
                        <select x-model="filters.category" @change="filterStories()" 
                                class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500">
                            <option value="">All Categories</option>
                            <template x-for="cat in categories" :key="cat">
                                <option :value="cat" x-text="cat"></option>
                            </template>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Source</label>
                        <select x-model="filters.source" @change="filterStories()"
                                class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500">
                            <option value="">All Sources</option>
                            <template x-for="source in sources" :key="source">
                                <option :value="source" x-text="source"></option>
                            </template>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Limit</label>
                        <select x-model="filters.limit" @change="loadStories()"
                                class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500">
                            <option value="25">25 stories</option>
                            <option value="50">50 stories</option>
                            <option value="100">100 stories</option>
                        </select>
                    </div>
                    <div class="flex items-end">
                        <button @click="loadStories()" :disabled="loading"
                                class="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg transition-colors">
                            <i class="fas fa-refresh mr-2" :class="{'fa-spin': loading}"></i>
                            <span x-text="loading ? 'Loading...' : 'Refresh'"></span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- Stories Grid -->
            <div class="grid gap-6" x-show="!loading" x-cloak>
                <template x-for="story in filteredStories" :key="story.id">
                    <article class="bg-white rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 overflow-hidden">
                        <div class="p-6">
                            <div class="flex items-start justify-between mb-4">
                                <div class="flex gap-2">
                                    <span class="bg-gradient-to-r from-blue-500 to-purple-600 text-white text-xs px-3 py-1 rounded-full font-medium"
                                          x-text="story.category || 'General'"></span>
                                    <span class="bg-gradient-to-r from-green-500 to-teal-600 text-white text-xs px-3 py-1 rounded-full font-medium"
                                          x-text="story.source || 'Unknown'"></span>
                                </div>
                                <time class="text-sm text-gray-500" x-text="formatDate(story.published)"></time>
                            </div>
                            
                            <h2 class="text-xl font-bold text-gray-900 mb-3 leading-tight">
                                <a :href="story.url" target="_blank" rel="noopener" 
                                   class="hover:text-blue-600 transition-colors" x-text="story.title"></a>
                            </h2>
                            
                            <p class="text-gray-700 mb-4 leading-relaxed" x-text="story.brief"></p>
                            
                            <div class="flex items-center justify-between pt-4 border-t border-gray-100">
                                <a :href="story.url" target="_blank" rel="noopener" 
                                   class="inline-flex items-center text-blue-600 hover:text-blue-800 font-medium transition-colors">
                                    Read Full Article
                                    <i class="fas fa-external-link-alt ml-2 text-sm"></i>
                                </a>
                                <div class="flex items-center gap-2">
                                    <span class="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded"
                                          x-text="'Score: ' + (story.relevance_score || 0).toFixed(1)"></span>
                                    <span class="text-xs text-gray-400" x-text="'Crawled: ' + formatDate(story.crawled_at)"></span>
                                </div>
                            </div>
                        </div>
                    </article>
                </template>
            </div>

            <!-- Loading State -->
            <div x-show="loading" class="text-center py-12">
                <i class="fas fa-spinner fa-spin text-4xl text-blue-600 mb-4"></i>
                <p class="text-gray-600 text-lg">Loading latest NIL news...</p>
            </div>

            <!-- Empty State -->
            <div x-show="!loading && filteredStories.length === 0" class="text-center py-12" x-cloak>
                <i class="fas fa-search text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-600 text-lg">No stories found matching your criteria.</p>
            </div>
        </div>
    </div>

    <script>
        function nilDashboard() {
            return {
                stories: [],
                filteredStories: [],
                loading: false,
                filters: {
                    category: '',
                    source: '',
                    limit: '50'
                },
                categories: [],
                sources: [],

                async loadStories() {
                    this.loading = true;
                    try {
                        const params = new URLSearchParams({
                            limit: this.filters.limit
                        });
                        
                        const response = await fetch(`/api/stories?${params}`);
                        const data = await response.json();
                        
                        this.stories = data;
                        this.updateFilters();
                        this.filterStories();
                    } catch (error) {
                        console.error('Error loading stories:', error);
                    } finally {
                        this.loading = false;
                    }
                },

                updateFilters() {
                    this.categories = [...new Set(this.stories.map(s => s.category).filter(Boolean))];
                    this.sources = [...new Set(this.stories.map(s => s.source).filter(Boolean))];
                },

                filterStories() {
                    this.filteredStories = this.stories.filter(story => {
                        if (this.filters.category && story.category !== this.filters.category) return false;
                        if (this.filters.source && story.source !== this.filters.source) return false;
                        return true;
                    });
                },

                formatDate(dateString) {
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
            }
        }

        // Auto-refresh every 5 minutes
        setInterval(() => {
            if (window.nilDashboard) {
                window.nilDashboard().loadStories();
            }
        }, 300000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Modern web dashboard."""
    return MODERN_HTML

@app.get("/api/stories")
async def get_stories(limit: int = 50, category: str = None, source: str = None):
    """Get stories with filtering."""
    conn = await asyncpg.connect(config.DATABASE_URL)
    
    query = """
        SELECT id, title, url, published, brief, source, category, crawled_at, relevance_score
        FROM stories
        WHERE 1=1
    """
    params = []
    
    if category:
        query += " AND category = $" + str(len(params) + 1)
        params.append(category)
    
    if source:
        query += " AND source = $" + str(len(params) + 1)
        params.append(source)
    
    query += f" ORDER BY published DESC NULLS LAST, crawled_at DESC LIMIT ${len(params) + 1}"
    params.append(limit)
    
    rows = await conn.fetch(query, *params)
    await conn.close()
    
    return [dict(row) for row in rows]

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Background crawling task
async def crawl_feeds():
    """Background task to crawl RSS feeds."""
    logger.info("Starting feed crawl...")
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for feed_url in config.FEEDS:
            try:
                response = await client.get(feed_url)
                feed = feedparser.parse(response.text)
                
                if feed.bozo:
                    logger.warning(f"Bad feed: {feed_url}")
                    continue
                
                for entry in feed.entries[:10]:  # Limit per feed
                    await process_entry(entry, feed_url)
                    
            except Exception as e:
                logger.error(f"Error processing feed {feed_url}: {e}")
    
    logger.info("Feed crawl completed")

async def process_entry(entry: dict, feed_url: str):
    """Process a single feed entry."""
    url = entry.get("link")
    if not url:
        return
    
    title = entry.get("title", "No title")
    content = entry.get("summary", "") + " " + entry.get("description", "")
    
    # Calculate relevance
    relevance = processor.calculate_relevance(title, content)
    if relevance < 1.0:  # Skip irrelevant content
        return
    
    # Extract metadata
    source = processor.extract_source(url)
    category = processor.categorize_content(title, content)
    
    # Parse date
    published = None
    if entry.get("published"):
        try:
            from email.utils import parsedate_to_datetime
            published = parsedate_to_datetime(entry["published"])
        except:
            pass
    
    # Store in database
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        await conn.execute("""
            INSERT INTO stories (id, title, url, published, brief, source, category, relevance_score)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (url) DO NOTHING
        """, 
        hashlib.sha256(url.encode()).hexdigest(),
        title,
        url,
        published,
        content[:500] + "..." if len(content) > 500 else content,
        source,
        category,
        relevance
        )
        logger.info(f"Stored: {title[:50]}... [{source}]")
    except Exception as e:
        logger.error(f"Database error: {e}")
    finally:
        await conn.close()

# Startup and background tasks
@app.on_event("startup")
async def startup():
    """Initialize app on startup."""
    await init_database()
    
    # Start background crawling if not in development
    if config.ENVIRONMENT != "development":
        asyncio.create_task(crawl_scheduler())

async def crawl_scheduler():
    """Schedule regular crawls."""
    while True:
        await crawl_feeds()
        await asyncio.sleep(config.CRAWL_INTERVAL * 60)

# Manual crawl endpoint
@app.post("/api/crawl")
async def manual_crawl(background_tasks: BackgroundTasks):
    """Trigger manual crawl."""
    background_tasks.add_task(crawl_feeds)
    return {"status": "crawl started"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
