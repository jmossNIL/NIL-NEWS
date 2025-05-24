#!/usr/bin/env python3
"""
Enhanced NIL News Aggregator with Deep Research & Twitter Integration
"""
import os
import asyncio
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import sqlite3

import aiosqlite
import feedparser
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, BackgroundTasks
from fastapi.responses import HTMLResponse
from trafilatura import extract
import httpx
import re

# Load environment variables
load_dotenv()

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
    "https://www.burntorangenation.com/feed/",
    "https://www.goodbullhunting.com/feed/",
    "https://www.stateoftheu.com/feed/",
    # Additional deep research feeds
    "https://www.athleticbusiness.com/feed/",
    "https://www.adweek.com/feed/",
    "https://marketingland.com/feed",
    "https://techcrunch.com/tag/sports/feed/",
]

KEYWORDS = [
    "nil", "name image likeness", "nil deal", "nil collective", "nil marketplace",
    "collective", "booster", "endorsement", "sponsorship", "brand deal",
    "student-athlete", "college athlete", "transfer portal", "recruiting",
    "house v ncaa", "house settlement", "opendorse", "marketpryce", "icon source",
    "social media influencer", "athlete influencer", "nil influencer",
    "ncaa", "compliance", "eligibility", "fair market value", "revenue sharing",
    "antitrust", "lawsuit", "settlement", "pay for play", "recruiting inducement",
]

# NIL-focused Twitter accounts to monitor
NIL_TWITTER_ACCOUNTS = [
    {
        "handle": "@NILWire",
        "name": "NIL Wire",
        "description": "Breaking NIL news and analysis",
        "url": "https://twitter.com/NILWire"
    },
    {
        "handle": "@On3NIL",
        "name": "On3 NIL",
        "description": "NIL news from On3",
        "url": "https://twitter.com/On3NIL"
    },
    {
        "handle": "@FrontOfficeSpts",
        "name": "Front Office Sports",
        "description": "Sports business news including NIL",
        "url": "https://twitter.com/FrontOfficeSpts"
    },
    {
        "handle": "@SBJ_NIL",
        "name": "Sports Business Journal NIL",
        "description": "NIL coverage from SBJ",
        "url": "https://twitter.com/SBJ_NIL"
    },
    {
        "handle": "@CollegeSportsIA",
        "name": "College Sports Business",
        "description": "College sports business and NIL analysis",
        "url": "https://twitter.com/CollegeSportsIA"
    },
    {
        "handle": "@OpendorseTeam",
        "name": "Opendorse",
        "description": "NIL marketplace platform",
        "url": "https://twitter.com/OpendorseTeam"
    },
    {
        "handle": "@MarketPryce",
        "name": "MarketPryce",
        "description": "NIL marketplace and analytics",
        "url": "https://twitter.com/MarketPryce"
    },
    {
        "handle": "@NILStore",
        "name": "NIL Store",
        "description": "Athlete merchandise and NIL deals",
        "url": "https://twitter.com/NILStore"
    },
    {
        "handle": "@TheAthletic",
        "name": "The Athletic",
        "description": "Sports journalism including NIL coverage",
        "url": "https://twitter.com/TheAthletic"
    },
    {
        "handle": "@SInow",
        "name": "Sports Illustrated",
        "description": "Sports news including NIL",
        "url": "https://twitter.com/SInow"
    }
]

DB_PATH = "nil_news.db"

# Enhanced Database setup
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
            category TEXT,
            relevance_score REAL DEFAULT 0.0,
            sentiment TEXT DEFAULT 'neutral',
            key_entities TEXT,
            breaking_news BOOLEAN DEFAULT 0
        )
    """)
    
    # Add new columns if they don't exist
    try:
        await db.execute("ALTER TABLE stories ADD COLUMN relevance_score REAL DEFAULT 0.0")
        await db.execute("ALTER TABLE stories ADD COLUMN sentiment TEXT DEFAULT 'neutral'")
        await db.execute("ALTER TABLE stories ADD COLUMN key_entities TEXT")
        await db.execute("ALTER TABLE stories ADD COLUMN breaking_news BOOLEAN DEFAULT 0")
    except:
        pass  # Columns already exist
    
    await db.commit()
    return db

# Enhanced Content processing
def calculate_relevance_score(title: str, text: str) -> float:
    """Calculate relevance score based on keyword importance and frequency."""
    content = (title + " " + text).lower()
    
    # High-value keywords (3 points each)
    high_value = ["nil deal", "nil collective", "house v ncaa", "nil endorsement", 
                  "nil settlement", "nil lawsuit", "breaking:", "exclusive:"]
    
    # Medium-value keywords (2 points each)
    medium_value = ["nil", "collective", "booster", "endorsement", "transfer portal",
                   "opendorse", "marketpryce"]
    
    # Low-value keywords (1 point each)
    low_value = ["college athlete", "student-athlete", "recruiting", "ncaa"]
    
    score = 0.0
    for keyword in high_value:
        score += content.count(keyword) * 3.0
    for keyword in medium_value:
        score += content.count(keyword) * 2.0
    for keyword in low_value:
        score += content.count(keyword) * 1.0
    
    # Bonus for recent breaking news indicators
    if any(indicator in content for indicator in ["breaking", "exclusive", "just in", "developing"]):
        score += 2.0
    
    return min(score, 15.0)  # Cap at 15

def extract_key_entities(title: str, text: str) -> List[str]:
    """Extract key entities like athlete names, schools, dollar amounts."""
    content = title + " " + text
    entities = []
    
    # Extract dollar amounts
    money_pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|thousand|M|B|K))?'
    money_matches = re.findall(money_pattern, content, re.IGNORECASE)
    entities.extend(money_matches)
    
    # Extract university names (common ones)
    universities = [
        "Alabama", "Georgia", "Texas", "Ohio State", "Michigan", "USC", "UCLA", 
        "Florida", "LSU", "Auburn", "Tennessee", "Kentucky", "Duke", "UNC",
        "Miami", "Oregon", "Washington", "Stanford", "Notre Dame", "Penn State"
    ]
    for uni in universities:
        if uni.lower() in content.lower():
            entities.append(uni)
    
    # Extract athlete names (basic pattern - Firstname Lastname)
    name_pattern = r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'
    potential_names = re.findall(name_pattern, content)
    # Filter out common false positives
    exclude_names = ["Sports Illustrated", "Front Office", "College Sports", "Business Journal"]
    for name in potential_names:
        if name not in exclude_names and len(name.split()) == 2:
            entities.append(name)
    
    return list(set(entities))[:10]  # Return unique entities, max 10

def detect_sentiment(title: str, text: str) -> str:
    """Simple sentiment detection."""
    content = (title + " " + text).lower()
    
    positive_words = ["record", "milestone", "success", "breakthrough", "major deal", 
                     "signing", "partnership", "expansion", "growth", "opportunity"]
    negative_words = ["lawsuit", "violation", "penalty", "suspended", "banned", 
                     "controversy", "scandal", "investigation", "denied", "rejected"]
    
    positive_count = sum(1 for word in positive_words if word in content)
    negative_count = sum(1 for word in negative_words if word in content)
    
    if positive_count > negative_count:
        return "positive"
    elif negative_count > positive_count:
        return "negative"
    else:
        return "neutral"

def is_breaking_news(title: str, text: str) -> bool:
    """Detect if this is breaking news."""
    content = (title + " " + text).lower()
    breaking_indicators = ["breaking", "just in", "developing", "exclusive", "first reported"]
    return any(indicator in content for indicator in breaking_indicators)

def is_relevant(text: str) -> bool:
    """Enhanced relevance checking."""
    text_lower = text.lower()
    keywords_lower = [k.lower() for k in KEYWORDS]
    
    # Require at least 2 keyword matches for better filtering
    matches = sum(1 for keyword in keywords_lower if keyword in text_lower)
    return matches >= 2

def categorize_content(title: str, text: str) -> str:
    """Enhanced content categorization."""
    combined = (title + " " + text).lower()
    
    categories = {
        "Breaking News": ["breaking", "just in", "developing", "exclusive"],
        "Legal": ["lawsuit", "settlement", "antitrust", "legal", "court", "house v ncaa"],
        "Collectives": ["collective", "booster", "donor", "fund"],
        "Technology": ["marketplace", "platform", "app", "technology", "opendorse", "marketpryce"],
        "Social Media": ["social media", "influencer", "instagram", "tiktok", "youtube"],
        "Recruiting": ["transfer portal", "recruiting", "prospect", "commit"],
        "High School": ["high school", "prep", "youth"],
        "Business": ["revenue", "deal", "contract", "partnership", "sponsorship", "valuation"],
        "Policy": ["ncaa", "compliance", "eligibility", "rules", "regulation"]
    }
    
    for category, keywords in categories.items():
        if any(keyword in combined for keyword in keywords):
            return category
    
    return "General"

def extract_source(url: str) -> str:
    """Enhanced source extraction."""
    try:
        source_map = {
            "frontofficesports.com": "Front Office Sports",
            "sportico.com": "Sportico",
            "businessofcollegesports.com": "Business of College Sports",
            "espn.com": "ESPN",
            "si.com": "Sports Illustrated",
            "news.google.com": "Google News",
            "athleticbusiness.com": "Athletic Business",
            "adweek.com": "Adweek",
            "marketingland.com": "Marketing Land",
            "techcrunch.com": "TechCrunch",
            "burntorangenation.com": "Burnt Orange Nation",
            "goodbullhunting.com": "Good Bull Hunting",
            "stateoftheu.com": "State of the U",
            "theatletic.com": "The Athletic"
        }
        
        for key, value in source_map.items():
            if key in url.lower():
                return value
        
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        return domain.replace("www.", "").replace(".com", "").title()
    except:
        return "Unknown"

def enhanced_summarize_text(text: str) -> str:
    """Enhanced text summarization with focus on key details."""
    # Clean and prepare text
    text = text.replace('\n', ' ').strip()
    sentences = [s.strip() + '.' for s in text.split('.') if len(s.strip()) > 20]
    
    # Prioritize sentences with key information
    priority_sentences = []
    regular_sentences = []
    
    for sentence in sentences[:10]:  # Only check first 10 sentences
        sentence_lower = sentence.lower()
        # High priority: money, names, deals, breaking news
        if any(indicator in sentence_lower for indicator in 
               ['$', 'deal', 'signed', 'announced', 'breaking', 'million', 'contract']):
            priority_sentences.append(sentence)
        else:
            regular_sentences.append(sentence)
    
    # Combine prioritized sentences first
    selected_sentences = priority_sentences[:2] + regular_sentences[:1]
    summary = ' '.join(selected_sentences[:3])
    
    return summary[:500] + "..." if len(summary) > 500 else summary

# Enhanced Crawler
async def crawl_feeds():
    """Enhanced crawling with better processing."""
    db = await init_db()
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        for feed_url in FEEDS:
            try:
                print(f"[info] Crawling {feed_url}")
                response = await client.get(feed_url)
                feed = feedparser.parse(response.text)
                
                if feed.bozo:
                    print(f"[warn] Bad feed: {feed_url}")
                    continue
                
                for entry in feed.entries[:8]:  # Increased limit per feed
                    await process_entry(entry, feed_url, db)
                    
            except Exception as e:
                print(f"[error] Failed to process {feed_url}: {e}")
    
    await db.close()
    print("[info] Enhanced crawl completed")

async def process_entry(entry: dict, feed_url: str, db):
    """Enhanced entry processing with deep analysis."""
    url = entry.get("link")
    if not url:
        return
    
    # Check if already exists
    story_id = hashlib.sha256(url.encode()).hexdigest()
    async with db.execute("SELECT 1 FROM stories WHERE id=?", (story_id,)) as cur:
        if await cur.fetchone():
            return
    
    title = entry.get("title", "No title")
    
    # Enhanced content extraction
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            text = extract(response.text) or response.text[:2000]
    except:
        text = entry.get("summary", "") + " " + entry.get("description", "")
    
    # Enhanced relevance checking
    if not is_relevant(title + " " + text):
        return
    
    # Deep analysis
    relevance_score = calculate_relevance_score(title, text)
    sentiment = detect_sentiment(title, text)
    key_entities = extract_key_entities(title, text)
    breaking = is_breaking_news(title, text)
    brief = enhanced_summarize_text(text)
    source = extract_source(url)
    category = categorize_content(title, text)
    published = entry.get("published", "")
    crawled_at = dt.datetime.utcnow().isoformat()
    
    # Store enhanced data
    await db.execute("""
        INSERT INTO stories VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (story_id, title, url, published, text[:3000], brief, crawled_at, 
          source, category, relevance_score, sentiment, json.dumps(key_entities), breaking))
    
    await db.commit()
    print(f"[+] Stored: {title[:50]}... [{source}] [Score: {relevance_score:.1f}] [Breaking: {breaking}]")

# FastAPI app
app = FastAPI(title="Enhanced NIL News Aggregator", version="3.0.0")

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
        .breaking-badge { animation: pulse 2s infinite; background: linear-gradient(45deg, #ff6b6b, #ee5a24); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
    </style>
</head>
<body class="bg-gray-50">
    <!-- Header -->
    <header class="gradient-bg text-white py-8">
        <div class="container mx-auto px-6">
            <h1 class="text-4xl font-bold mb-2">
                <i class="fas fa-newspaper mr-3"></i>NIL News Hub Pro
            </h1>
            <p class="text-blue-100">Advanced NIL news aggregation with deep research & Twitter monitoring</p>
        </div>
    </header>

    <!-- Tabs -->
    <div class="container mx-auto px-6 pt-6">
        <div class="bg-white rounded-lg shadow-md mb-6">
            <div class="flex border-b">
                <button onclick="showTab('news')" id="news-tab" class="tab-active px-6 py-3 font-medium rounded-tl-lg">
                    <i class="fas fa-newspaper mr-2"></i>News Feed
                </button>
                <button onclick="showTab('twitter')" id="twitter-tab" class="px-6 py-3 font-medium hover:bg-gray-50">
                    <i class="fab fa-twitter mr-2"></i>Twitter Monitoring
                </button>
                <button onclick="showTab('research')" id="research-tab" class="px-6 py-3 font-medium hover:bg-gray-50">
                    <i class="fas fa-search mr-2"></i>Deep Research
                </button>
                <button onclick="showTab('analytics')" id="analytics-tab" class="px-6 py-3 font-medium hover:bg-gray-50 rounded-tr-lg">
                    <i class="fas fa-chart-bar mr-2"></i>Analytics
                </button>
            </div>
        </div>

        <!-- News Tab -->
        <div id="news-content" class="tab-content">
            <div class="bg-white rounded-lg shadow-md p-4 mb-6">
                <div class="flex gap-4 items-center flex-wrap">
                    <button onclick="refreshStories()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-refresh mr-2"></i>Refresh
                    </button>
                    <button onclick="crawlNow()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-download mr-2"></i>Deep Crawl
                    </button>
                    <select id="category-filter" onchange="filterStories()" class="border border-gray-300 rounded-lg px-3 py-2">
                        <option value="">All Categories</option>
                        <option value="Breaking News">Breaking News</option>
                        <option value="Legal">Legal</option>
                        <option value="Collectives">Collectives</option>
                        <option value="Technology">Technology</option>
                        <option value="Business">Business</option>
                    </select>
                    <select id="sentiment-filter" onchange="filterStories()" class="border border-gray-300 rounded-lg px-3 py-2">
                        <option value="">All Sentiment</option>
                        <option value="positive">Positive</option>
                        <option value="neutral">Neutral</option>
                        <option value="negative">Negative</option>
                    </select>
                    <span id="story-count" class="text-gray-600"></span>
                </div>
            </div>

            <div id="stories-container">
                <div class="text-center py-8">
                    <i class="fas fa-spinner fa-spin text-2xl text-blue-600"></i>
                    <p class="text-gray-600 mt-2">Loading enhanced news feed...</p>
                </div>
            </div>
        </div>

        <!-- Twitter Tab -->
        <div id="twitter-content" class="tab-content hidden">
            <div class="bg-white rounded-lg shadow-md p-6 mb-6">
                <h3 class="text-xl font-bold mb-4">NIL Twitter Accounts to Follow</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    ${NIL_TWITTER_ACCOUNTS.map(account => `
                        <div class="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                            <div class="flex items-start justify-between mb-2">
                                <h4 class="font-bold text-blue-600">${account.handle}</h4>
                                <a href="${account.url}" target="_blank" class="text-blue-500 hover:text-blue-700">
                                    <i class="fab fa-twitter"></i>
                                </a>
                            </div>
                            <p class="font-medium text-gray-800 mb-1">${account.name}</p>
                            <p class="text-gray-600 text-sm">${account.description}</p>
                            <a href="${account.url}" target="_blank" 
                               class="inline-block mt-2 bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded text-sm">
                                Follow
                            </a>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>

        <!-- Research Tab -->
        <div id="research-content" class="tab-content hidden">
            <div class="bg-white rounded-lg shadow-md p-6">
                <h3 class="text-xl font-bold mb-4">Deep Research Tools</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="border border-gray-200 rounded-lg p-4">
                        <h4 class="font-bold mb-2">Trending Entities</h4>
                        <div id="trending-entities">Loading...</div>
                    </div>
                    <div class="border border-gray-200 rounded-lg p-4">
                        <h4 class="font-bold mb-2">Story Sources</h4>
                        <div id="source-breakdown">Loading...</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Analytics Tab -->
        <div id="analytics-content" class="tab-content hidden">
            <div class="bg-white rounded-lg shadow-md p-6">
                <h3 class="text-xl font-bold mb-4">NIL News Analytics</h3>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div class="text-center">
                        <div class="text-3xl font-bold text-blue-600" id="total-stories">0</div>
                        <div class="text-gray-500">Total Stories</div>
                    </div>
                    <div class="text-center">
                        <div class="text-3xl font-bold text-green-600" id="breaking-stories">0</div>
                        <div class="text-gray-500">Breaking News</div>
                    </div>
                    <div class="text-center">
                        <div class="text-3xl font-bold text-purple-600" id="avg-relevance">0.0</div>
                        <div class="text-gray-500">Avg Relevance</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let allStories = [];
        let currentTab = 'news';

        function showTab(tabName) {
            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('[id$="-tab"]').forEach(el => el.classList.remove('tab-active', 'px-6', 'py-3', 'font-medium'));
            
            // Show selected tab
            document.getElementById(tabName + '-content').classList.remove('hidden');
            document.getElementById(tabName + '-tab').classList.add('tab-active');
            
            currentTab = tabName;
            
            if (tabName === 'research') {
                loadResearchData();
            } else if (tabName === 'analytics') {
                loadAnalytics();
            }
        }

        async function loadStories() {
            try {
                const response = await fetch('/api/summaries?limit=100');
                const stories = await response.json();
                allStories = stories;
                
                document.getElementById('story-count').textContent = `${stories.length} stories loaded`;
                filterStories();
                
            } catch (error) {
                console.error('Error loading stories:', error);
                document.getElementById('stories-container').innerHTML = 
                    '<div class="text-center text-red-500 py-8">Error loading stories</div>';
            }
        }

        function filterStories() {
            const categoryFilter = document.getElementById('category-filter').value;
            const sentimentFilter = document.getElementById('sentiment-filter').value;
            
            let filteredStories = allStories.filter(story => {
                if (categoryFilter && story.category !== categoryFilter) return false;
                if (sentimentFilter && story.sentiment !== sentimentFilter) return false;
                return true;
            });

            // Smart sorting: Recent + Relevant stories first
            filteredStories.sort((a, b) => {
                const now = new Date();
                const dateA = new Date(a.published || a.crawled_at || 0);
                const dateB = new Date(b.published || b.crawled_at || 0);
                
                // Calculate smart scores (recency + relevance)
                const scoreA = calculateSmartScore(a, dateA, now);
                const scoreB = calculateSmartScore(b, dateB, now);
                
                // If scores are very close (within 5 points), sort by date
                if (Math.abs(scoreA - scoreB) < 5) {
                    return dateB - dateA; // Newer first
                }
                
                return scoreB - scoreA; // Higher score first
            });
        }

        function calculateSmartScore(story, storyDate, now) {
            let score = 0;
            
            // Breaking news bonus (last 24 hours only)
            const hoursAgo = (now - storyDate) / (1000 * 60 * 60);
            if (story.breaking_news && hoursAgo < 24) {
                score += 1000;
            }
            
            // Recency bonus
            const daysAgo = hoursAgo / 24;
            if (daysAgo < 1) score += 50;        // Last 24 hours
            else if (daysAgo < 3) score += 30;   // Last 3 days  
            else if (daysAgo < 7) score += 20;   // Last week
            else if (daysAgo < 14) score += 10;  // Last 2 weeks
            
            // Add relevance score
            score += (story.relevance_score || 0);
            
            return score;
        }

            const container = document.getElementById('stories-container');
            
            if (filteredStories.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <p class="text-gray-600">No stories match your filters. Try adjusting your criteria or click "Deep Crawl"!</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = filteredStories.map(story => `
                <article class="bg-white rounded-lg shadow-md hover:shadow-lg card-hover p-6 mb-6">
                    <div class="flex items-start justify-between mb-4">
                        <div class="flex gap-2 flex-wrap">
                            ${story.breaking_news ? '<span class="breaking-badge text-white text-xs px-2 py-1 rounded-full font-medium">🚨 BREAKING</span>' : ''}
                            <span class="bg-blue-500 text-white text-xs px-2 py-1 rounded-full">
                                ${story.category || 'General'}
                            </span>
                            <span class="bg-green-500 text-white text-xs px-2 py-1 rounded-full">
                                ${story.source || 'Unknown'}
                            </span>
                            <span class="bg-purple-500 text-white text-xs px-2 py-1 rounded-full">
                                ${(story.relevance_score || 0).toFixed(1)} ⭐
                            </span>
                            <span class="bg-${story.sentiment === 'positive' ? 'green' : story.sentiment === 'negative' ? 'red' : 'gray'}-500 text-white text-xs px-2 py-1 rounded-full">
                                ${story.sentiment || 'neutral'}
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
                    
                    ${story.key_entities ? `
                        <div class="mb-4">
                            <span class="text-sm font-medium text-gray-600">Key Entities: </span>
                            ${JSON.parse(story.key_entities || '[]').map(entity => 
                                `<span class="inline-block bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded mr-1 mb-1">${entity}</span>`
                            ).join('')}
                        </div>
                    ` : ''}
                    
                    <a href="${story.url}" target="_blank" 
                       class="inline-flex items-center text-blue-600 hover:text-blue-800 font-medium">
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
                document.querySelector('button[onclick="crawlNow()"]').innerHTML = 
                    '<i class="fas fa-spinner fa-spin mr-2"></i>Crawling...';
                
                const response = await fetch('/api/crawl', { method: 'POST' });
                if (response.ok) {
                    alert('Deep crawl started! This will take 2-3 minutes. Refresh to see new stories.');
                }
            } catch (error) {
                alert('Error starting crawl');
            } finally {
                document.querySelector('button[onclick="crawlNow()"]').innerHTML = 
                    '<i class="fas fa-download mr-2"></i>Deep Crawl';
            }
        }

        async function loadResearchData() {
            try {
                // Load trending entities
                const entitiesResponse = await fetch('/api/trending-entities');
                const entities = await entitiesResponse.json();
                
                document.getElementById('trending-entities').innerHTML = entities.map(entity => 
                    `<div class="flex justify-between items-center py-1">
                        <span class="text-sm">${entity.entity}</span>
                        <span class="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded">${entity.count}</span>
                    </div>`
                ).join('');

                // Load source breakdown
                const sourcesResponse = await fetch('/api/source-breakdown');
                const sources = await sourcesResponse.json();
                
                document.getElementById('source-breakdown').innerHTML = sources.map(source => 
                    `<div class="flex justify-between items-center py-1">
                        <span class="text-sm">${source.source}</span>
                        <span class="bg-green-100 text-green-800 text-xs px-2 py-1 rounded">${source.count}</span>
                    </div>`
                ).join('');

            } catch (error) {
                console.error('Error loading research data:', error);
            }
        }

        async function loadAnalytics() {
            try {
                const response = await fetch('/api/analytics');
                const analytics = await response.json();
                
                document.getElementById('total-stories').textContent = analytics.total_stories;
                document.getElementById('breaking-stories').textContent = analytics.breaking_stories;
                document.getElementById('avg-relevance').textContent = analytics.avg_relevance.toFixed(1);

            } catch (error) {
                console.error('Error loading analytics:', error);
            }
        }
        
        function formatDate(dateString) {
            if (!dateString) return 'Unknown';
            const date = new Date(dateString);
            const now = new Date();
            const diff = now - date;
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const days = Math.floor(hours / 24);
            
            if (hours < 1) return 'Just now';
            if (hours < 24) return `${hours}h ago`;
            if (days < 7) return `${days}d ago`;
            return date.toLocaleDateString();
        }
        
        // Load initial data
        loadStories();
        
        // Auto-refresh every 3 minutes
        setInterval(loadStories, 180000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Enhanced web dashboard with tabs."""
    # Replace Twitter accounts in template
    twitter_accounts_js = json.dumps(NIL_TWITTER_ACCOUNTS)
    html = HTML_TEMPLATE.replace('${NIL_TWITTER_ACCOUNTS.map(account =>', 
                                f'{twitter_accounts_js}.map(account =>')
    return html

@app.get("/api/summaries")
async def get_summaries(limit: int = 100):
    """Get enhanced story summaries."""
    db = await aiosqlite.connect(DB_PATH)
    
    async with db.execute("""
        SELECT title, url, published, brief, source, category, crawled_at,
               relevance_score, sentiment, key_entities, breaking_news,
               CASE 
                   WHEN published IS NOT NULL AND published != '' 
                   THEN datetime(published) 
                   ELSE datetime(crawled_at) 
               END as sort_date
        FROM stories
        ORDER BY 
            -- Breaking news from last 24 hours gets top priority
            CASE WHEN breaking_news = 1 AND sort_date > datetime('now', '-1 day') THEN 1000 ELSE 0 END +
            -- Recency bonus: stories from last 24 hours get 50 points, last week gets 20 points
            CASE 
                WHEN sort_date > datetime('now', '-1 day') THEN 50
                WHEN sort_date > datetime('now', '-3 days') THEN 30  
                WHEN sort_date > datetime('now', '-7 days') THEN 20
                WHEN sort_date > datetime('now', '-14 days') THEN 10
                ELSE 0 
            END +
            -- Add relevance score (0-15 points)
            COALESCE(relevance_score, 0)
            DESC,
            -- Secondary sort by actual date for ties
            sort_date DESC
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
            "crawled_at": row[6],
            "relevance_score": row[7],
            "sentiment": row[8],
            "key_entities": row[9],
            "breaking_news": bool(row[10])
        }
        for row in rows
    ]

@app.get("/api/trending-entities")
async def get_trending_entities():
    """Get trending entities from recent stories."""
    db = await aiosqlite.connect(DB_PATH)
    
    # Get all entities from recent stories
    async with db.execute("""
        SELECT key_entities FROM stories 
        WHERE crawled_at > datetime('now', '-7 days')
        AND key_entities IS NOT NULL
    """) as cur:
        rows = await cur.fetchall()
    
    await db.close()
    
    # Count entity occurrences
    entity_counts = {}
    for row in rows:
        if row[0]:
            entities = json.loads(row[0])
            for entity in entities:
                entity_counts[entity] = entity_counts.get(entity, 0) + 1
    
    # Sort by frequency and return top 10
    trending = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return [{"entity": entity, "count": count} for entity, count in trending]

@app.get("/api/source-breakdown")
async def get_source_breakdown():
    """Get breakdown of stories by source."""
    db = await aiosqlite.connect(DB_PATH)
    
    async with db.execute("""
        SELECT source, COUNT(*) as count
        FROM stories
        WHERE crawled_at > datetime('now', '-7 days')
        GROUP BY source
        ORDER BY count DESC
        LIMIT 10
    """) as cur:
        rows = await cur.fetchall()
    
    await db.close()
    
    return [{"source": row[0], "count": row[1]} for row in rows]

@app.get("/api/analytics")
async def get_analytics():
    """Get analytics dashboard data."""
    db = await aiosqlite.connect(DB_PATH)
    
    # Get various statistics
    async with db.execute("SELECT COUNT(*) FROM stories") as cur:
        total_stories = (await cur.fetchone())[0]
    
    async with db.execute("SELECT COUNT(*) FROM stories WHERE breaking_news = 1") as cur:
        breaking_stories = (await cur.fetchone())[0]
    
    async with db.execute("SELECT AVG(relevance_score) FROM stories WHERE relevance_score > 0") as cur:
        avg_relevance = (await cur.fetchone())[0] or 0.0
    
    await db.close()
    
    return {
        "total_stories": total_stories,
        "breaking_stories": breaking_stories,
        "avg_relevance": avg_relevance
    }

@app.post("/api/crawl")
async def manual_crawl():
    """Trigger enhanced manual crawl."""
    asyncio.create_task(crawl_feeds())
    return {"status": "enhanced crawl started"}

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "version": "3.0.0"}

# Background crawling
async def background_crawler():
    """Enhanced background crawler."""
    while True:
        try:
            await crawl_feeds()
            await asyncio.sleep(180)  # 3 minutes
        except Exception as e:
            print(f"[error] Background crawler failed: {e}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup():
    """Start enhanced background tasks."""
    await init_db()
    asyncio.create_task(background_crawler())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
