import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import os

# --- 設定 ---
INTEREST_KEYWORDS = [
    "Claude", "React", "Python", "Vite", "TypeScript", "LLM", "AI",
    "Obsidian", "FF14", "XIV"
]
BOOST_SCORE = 15

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "public", "data.json")

# User-Agent は偽装しないとブロックされることが多い
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def fetch_xml(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return ET.fromstring(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def calculate_boost(title):
    boost = 0
    title_lower = title.lower()
    for kw in INTEREST_KEYWORDS:
        if kw.lower() in title_lower:
            boost += BOOST_SCORE
            break # 複数ヒットしてもブーストは1回分にするか、加算するか。今回は加算しない
    return boost

def normalize_score(value, min_val, max_val):
    if max_val == min_val:
        return 50 # fallback
    score = (value - min_val) / (max_val - min_val) * 100
    return min(max(score, 0), 100)

def fetch_zenn():
    print("Fetching Zenn...")
    data = fetch_json("https://zenn.dev/api/articles?order=daily")
    if not data or "articles" not in data:
        return []
    
    results = []
    for item in data["articles"][:20]:
        title = item.get("title", "")
        url = f"https://zenn.dev{item.get('path', '')}"
        likes = item.get("liked_count", 0)
        
        results.append({
            "source": "Zenn",
            "title": title,
            "url": url,
            "raw_score": likes,
            "published_at": item.get("published_at", "")
        })
    return results

def fetch_qiita():
    print("Fetching Qiita...")
    # Atom Feed
    root = fetch_xml("https://qiita.com/popular-items/feed")
    if not root:
        return []
    
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    
    for entry in root.findall("atom:entry", ns)[:20]:
        title = entry.find("atom:title", ns).text
        url = entry.find("atom:link", ns).get("href")
        published = entry.find("atom:published", ns).text
        
        # Qiita feed doesn't have likes count easily accessible without API token
        # So we mock a raw score based on its order in the popular feed
        results.append({
            "source": "Qiita",
            "title": title,
            "url": url,
            "raw_score": 0, # Will handle in normalization
            "published_at": published
        })
    return results

def fetch_hatebu():
    print("Fetching Hatebu...")
    # RSS 1.0
    root = fetch_xml("https://b.hatena.ne.jp/hotentry/it.rss")
    if not root:
        return []
    
    ns = {
        "rss": "http://purl.org/rss/1.0/",
        "hatena": "http://www.hatena.ne.jp/info/xmlns#",
        "dc": "http://purl.org/dc/elements/1.1/"
    }
    results = []
    for item in root.findall(".//rss:item", ns)[:20]:
        title = item.find("rss:title", ns).text
        url = item.find("rss:link", ns).text
        bookmark_count = int(item.find("hatena:bookmarkcount", ns).text or 0)
        
        # Dublin Core (dc:date) から日付を取得
        published_at = ""
        dc_date = item.find("dc:date", ns)
        if dc_date is not None and dc_date.text:
            published_at = dc_date.text
        
        results.append({
            "source": "Hatebu",
            "title": title,
            "url": url,
            "raw_score": bookmark_count,
            "published_at": published_at
        })
    return results

def fetch_hackernews():
    print("Fetching Hacker News...")
    top_ids = fetch_json("https://hacker-news.firebaseio.com/v0/topstories.json")
    if not top_ids:
        return []
    
    results = []
    for item_id in top_ids[:15]:
        item = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
        if item:
            results.append({
                "source": "HackerNews",
                "title": item.get("title", ""),
                "url": item.get("url", f"https://news.ycombinator.com/item?id={item_id}"),
                "raw_score": item.get("score", 0),
                "published_at": datetime.fromtimestamp(item.get("time", 0), timezone.utc).isoformat()
            })
    return results

def fetch_reddit(subreddit):
    print(f"Fetching Reddit r/{subreddit}...")
    data = fetch_json(f"https://old.reddit.com/r/{subreddit}/hot.json?limit=15")
    if not data or "data" not in data:
        return []
    
    results = []
    for child in data["data"]["children"]:
        item = child["data"]
        # Skip stickied posts
        if item.get("stickied", False):
            continue
            
        results.append({
            "source": f"Reddit: r/{subreddit}",
            "title": item.get("title", ""),
            "url": f"https://old.reddit.com{item.get('permalink', '')}",
            "raw_score": item.get("score", 0),
            "published_at": datetime.fromtimestamp(item.get("created_utc", 0), timezone.utc).isoformat()
        })
    return results

def main():
    all_articles = []
    
    # 1. Fetch data
    zenn_data = fetch_zenn()
    qiita_data = fetch_qiita()
    hatebu_data = fetch_hatebu()
    hn_data = fetch_hackernews()
    obsidian_data = fetch_reddit("ObsidianMD")
    ffxiv_data = fetch_reddit("ffxiv")
    
    # 2. Normalize scores per source
    sources = {
        "Zenn": zenn_data,
        "Qiita": qiita_data,
        "Hatebu": hatebu_data,
        "HackerNews": hn_data,
        "Reddit: r/ObsidianMD": obsidian_data,
        "Reddit: r/ffxiv": ffxiv_data
    }
    
    for source_name, articles in sources.items():
        if not articles:
            continue
            
        if source_name == "Qiita":
            # For Qiita where we don't have scores, just assign decreasing scores
            for i, article in enumerate(articles):
                article["normalized_score"] = 100 - (i * 5)
        else:
            scores = [a["raw_score"] for a in articles]
            min_score = min(scores) if scores else 0
            max_score = max(scores) if scores else 1
            
            for article in articles:
                norm = normalize_score(article["raw_score"], min_score, max_score)
                article["normalized_score"] = round(norm, 1)
        
        # Apply keyword boost
        for article in articles:
            boost = calculate_boost(article["title"])
            article["normalized_score"] = min(article["normalized_score"] + boost, 100)
            article["is_boosted"] = boost > 0
            
        all_articles.extend(articles)
        
    # 3. Sort by score
    all_articles.sort(key=lambda x: x["normalized_score"], reverse=True)
    
    # Ensure public dir exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # 4. Output JSON
    output_data = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "articles": all_articles
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully generated {OUTPUT_FILE} with {len(all_articles)} articles.")

if __name__ == "__main__":
    main()
