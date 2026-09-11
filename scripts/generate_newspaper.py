#!/usr/bin/env python
"""
tech-news-digest 向け新聞生成 ＆ データ更新スクリプト
- public/morning.html （朝刊）生成
- public/evening.html （夕刊）生成
- public/data.json （Reactポータル用データ）更新
"""
import os
import sys
import json
import urllib.parse
import urllib.request
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from jinja2 import Environment, FileSystemLoader
import yaml
import logging

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NewspaperGenerator")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())

def get_hatena_bookmark_count(url: str) -> int:
    try:
        api_url = f"https://bookmark.hatenaapis.com/count/entry?url={urllib.parse.quote(url)}"
        res = requests.get(api_url, headers=HEADERS, timeout=3)
        if res.status_code == 200 and res.text.isdigit():
            return int(res.text)
    except Exception:
        pass
    return 0

def fetch_rss_feed(url: str, source_name: str, max_items: int = 15) -> list[dict]:
    logger.info(f"RSS取得中: {source_name} ({url})")
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            
            summary = ""
            if "summary" in entry:
                summary = clean_html(entry.summary)
            elif "description" in entry:
                summary = clean_html(entry.description)
            elif "content" in entry and len(entry.content) > 0:
                summary = clean_html(entry.content[0].value)

            if not title or not link:
                continue

            pub_date = entry.get("published", "") or entry.get("updated", "")

            items.append({
                "title": title,
                "url": link,
                "source": source_name,
                "summary": summary[:250] if summary else title,
                "published_at": pub_date,
                "hatebu_count": 0
            })
    except Exception as e:
        logger.warning(f"RSS取得エラー [{source_name}]: {e}")
    return items

def fetch_google_news(query: str, source_name: str, max_items: int = 15) -> list[dict]:
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    logger.info(f"Google News取得中: {source_name} (Query: {query})")
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = clean_html(entry.get("summary", ""))

            actual_source = source_name
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0].strip()
                actual_source = parts[1].strip()

            if not title or not link:
                continue

            items.append({
                "title": title,
                "url": link,
                "source": actual_source,
                "summary": summary[:250] if summary else title,
                "published_at": entry.get("published", ""),
                "hatebu_count": 0
            })
    except Exception as e:
        logger.warning(f"Google News取得エラー [{source_name}]: {e}")
    return items

def fetch_category_articles(category_key: str, cat_config: dict, max_per_source: int = 8) -> list[dict]:
    raw_articles = []
    seen_urls = set()
    seen_titles = set()

    for src in cat_config.get("sources", []):
        src_type = src.get("type", "rss")
        src_name = src.get("name", "Web")
        
        if src_type == "rss":
            items = fetch_rss_feed(src["url"], src_name, max_items=max_per_source)
        elif src_type == "google_news":
            items = fetch_google_news(src["query"], src_name, max_items=max_per_source)
        else:
            items = []

        for item in items:
            title_norm = item["title"][:20].lower()
            if item["url"] in seen_urls or title_norm in seen_titles:
                continue
            seen_urls.add(item["url"])
            seen_titles.add(title_norm)
            
            item["hatebu_count"] = get_hatena_bookmark_count(item["url"])
            raw_articles.append(item)

    return raw_articles

def calculate_article_score(article: dict, category_key: str, rules: dict) -> float:
    weights = rules.get("weights", {"popularity": 0.4, "impact": 0.6})
    w_pop = weights.get("popularity", 0.4)
    w_imp = weights.get("impact", 0.6)

    hatebu = article.get("hatebu_count", 0)
    if hatebu >= 100:
        pop_score = 45.0
    elif hatebu >= 50:
        pop_score = 35.0
    elif hatebu >= 20:
        pop_score = 25.0
    elif hatebu >= 5:
        pop_score = 15.0
    elif hatebu >= 1:
        pop_score = 8.0
    else:
        pop_score = 5.0

    cat_rules = rules.get("categories", {}).get(category_key, {})
    imp_score = 10.0
    
    text_to_check = f"{article.get('title', '')} {article.get('summary', '')}".lower()

    for kw_group in cat_rules.get("high_priority_keywords", []):
        score_val = kw_group.get("score", 10)
        for w in kw_group.get("words", []):
            if w.lower() in text_to_check:
                imp_score += score_val
                break

    for kw_group in cat_rules.get("penalty_keywords", []):
        score_val = kw_group.get("score", -10)
        for w in kw_group.get("words", []):
            if w.lower() in text_to_check:
                imp_score += score_val

    final_score = (pop_score * w_pop) + (imp_score * w_imp)
    return round(final_score, 1)

def rank_and_filter_articles(articles: list[dict], category_key: str, rules: dict, top_n: int = 5) -> list[dict]:
    scored = []
    for art in articles:
        f_score = calculate_article_score(art, category_key, rules)
        if f_score <= 0:
            continue
        art_copy = dict(art)
        art_copy["score"] = f_score
        scored.append(art_copy)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]

def generate_business_impact(article: dict, category_key: str, edition: str = "morning") -> str:
    title = article.get("title", "")
    summary = article.get("summary", "")
    text = f"{title} {summary}".lower()

    if category_key == "ai":
        if any(w in text for w in ["claude", "gpt", "gemini", "llm", "モデル"]):
            return "→ 最新モデルの性能検証と既存プロンプトの改修検討"
        elif any(w in text for w in ["agent", "エージェント", "code", "cursor", "自動化"]):
            return "→ コーディング・定常業務へのエージェント導入検証が急務"
        elif any(w in text for w in ["rag", "検索", "データベース", "ナレッジ"]):
            return "→ 社内ナレッジ連携の精度向上施策への取り込み"
        elif any(w in text for w in ["セキュリティ", "脆弱性", "規約", "著作権"]):
            return "→ AI利用ガイドラインと社内セキュリティ運用の確認"
        else:
            return "→ 業務効率化ツールとしての実務適用可能性を調査"

    elif category_key == "water":
        if any(w in text for w in ["ppp", "pfi", "官民連携", "民間委託"]):
            return "→ ウォーターPPP推進方針と自治体公募案件の動向注視"
        elif any(w in text for w in ["スマートメーター", "dx", "デジタル", "遠隔", "ai"]):
            return "→ 検針・漏水監視DXの先行導入事例のベンチマーク"
        elif any(w in text for w in ["耐震", "老朽化", "管路更新", "更新"]):
            return "→ 管路更新優先度判定および長寿命化計画の進捗確認"
        elif any(w in text for w in ["水質", "浄水", "下水", "資源化", "汚泥"]):
            return "→ 環境基準対応と省エネ型水処理技術の情報収集"
        else:
            return "→ 上下水道広域化・持続可能インフラ政策の波及影響確認"

    elif category_key == "ff14":
        if any(w in text for w in ["パッチ", "アップデート", "7.", "パッチノート"]):
            return "→ アップデート内容の確認と新コンテンツ攻略の計画"
        elif any(w in text for w in ["pll", "プロデューサーレター", "吉田"]):
            return "→ 次期ロードマップ・調整内容のアーカイブ視聴"
        elif any(w in text for w in ["メンテナンス", "障害"]):
            return "→ メンテ時間帯の確認と日課（ルレ・蛮族）の消化タイミング調整"
        elif any(w in text for w in ["イベント", "モグコレ", "シーズナル"]):
            return "→ 期間限定報酬の取得条件と期間のスケジュール化"
        else:
            return "→ コミュニティ動向とトレンド装備・金策情報のチェック"

    elif category_key == "game":
        if any(w in text for w in ["セール", "無料", "steam", "switch", "ps5"]):
            return "→ ウィッシュリスト登録・プレイ予定タイトルの価格動向確認"
        elif any(w in text for w in ["新作", "発表", "発売日", "トレーラー"]):
            return "→ ゲームプレイトレーラーとシステム仕様の先行チェック"
        elif any(w in text for w in ["レビュー", "評価", "goty"]):
            return "→ UI/UX設計やゲームメカニクス評価のインプット"
        elif any(w in text for w in ["開発", "unreal", "unity", "インタビュー"]):
            return "→ 最新描画エンジン技術やゲーム開発手法の知見蓄積"
        else:
            return "→ エンタメ市場のトレンド把握とリフレッシュ用候補の確保"

    return "→ 関連動向の定期モニタリングとナレッジ蓄積"

def main():
    os.makedirs(PUBLIC_DIR, exist_ok=True)

    with open(os.path.join(CONFIG_DIR, "sources.yaml"), "r", encoding="utf-8") as f:
        sources_config = yaml.safe_load(f)

    with open(os.path.join(CONFIG_DIR, "scoring_rules.yaml"), "r", encoding="utf-8") as f:
        scoring_rules = yaml.safe_load(f)

    categories = sources_config.get("categories", {})
    categories_data = {}
    all_react_articles = []

    logger.info("4大特化カテゴリの記事収集＆スコアリングを開始...")

    for cat_key, cat_info in categories.items():
        cat_name = cat_info.get("name", cat_key)
        cat_icon = cat_info.get("icon", "📌")
        logger.info(f"[{cat_icon} {cat_name}] 収集中...")

        raw_articles = fetch_category_articles(cat_key, cat_info, max_per_source=8)
        ranked = rank_and_filter_articles(raw_articles, cat_key, scoring_rules, top_n=5)

        for art in ranked:
            art["business_impact"] = generate_business_impact(art, cat_key)
            all_react_articles.append({
                "source": f"{cat_icon} {art['source']}",
                "category": cat_name,
                "category_key": cat_key,
                "title": art["title"],
                "url": art["url"],
                "summary": art.get("summary", ""),
                "business_impact": art["business_impact"],
                "raw_score": art.get("hatebu_count", 0),
                "normalized_score": art.get("score", 50),
                "published_at": art.get("published_at", "")
            })

        categories_data[cat_key] = {
            "name": cat_name,
            "icon": cat_icon,
            "articles": ranked
        }

    # Jinja2 テンプレート環境
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    now = datetime.now()
    issue_date = now.strftime("%Y年%m月%d日")
    issue_number = int(now.strftime("%Y%m%d"))

    # 全体最高スコア記事
    all_articles_flat = [a for c in categories_data.values() for a in c["articles"]]
    top_headline = max(all_articles_flat, key=lambda x: x.get("score", 0)) if all_articles_flat else None

    # 1. public/morning.html 出力
    morning_tmpl = env.get_template("morning.html")
    morning_html = morning_tmpl.render(
        newspaper_title="日刊パーソナルタイムズ",
        edition="morning",
        issue_date=issue_date,
        issue_number=issue_number,
        categories=categories_data,
        top_headline=top_headline
    )
    with open(os.path.join(PUBLIC_DIR, "morning.html"), "w", encoding="utf-8") as f:
        f.write(morning_html)
    logger.info(" [OK] public/morning.html を生成しました。")

    # 2. public/evening.html 出力
    evening_tmpl = env.get_template("evening.html")
    evening_html = evening_tmpl.render(
        newspaper_title="日刊パーソナルタイムズ",
        edition="evening",
        issue_date=issue_date,
        issue_number=issue_number,
        categories=categories_data,
        top_headline=top_headline
    )
    with open(os.path.join(PUBLIC_DIR, "evening.html"), "w", encoding="utf-8") as f:
        f.write(evening_html)
    logger.info(" [OK] public/evening.html を生成しました。")

    # 3. public/data.json 出力（Reactアプリ用）
    data_json = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "articles": all_react_articles
    }
    with open(os.path.join(PUBLIC_DIR, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data_json, f, ensure_ascii=False, indent=2)
    logger.info(" [OK] public/data.json を更新しました。")

if __name__ == "__main__":
    main()
