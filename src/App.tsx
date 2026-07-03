import { useState, useEffect } from 'react'
import './index.css'

interface Article {
  source: string;
  title: string;
  url: string;
  raw_score: number;
  normalized_score: number;
  published_at: string;
  is_boosted?: boolean;
}

interface DataJson {
  generated_at: string;
  articles: Article[];
}

function App() {
  const [data, setData] = useState<DataJson | null>(null);
  const [activeTab, setActiveTab] = useState<string>('Top');
  const [savedUrls, setSavedUrls] = useState<Set<string>>(new Set());
  const [recentOnly, setRecentOnly] = useState<boolean>(false);

  useEffect(() => {
    fetch('/data.json')
      .then(res => res.json())
      .then(json => setData(json))
      .catch(err => console.error("Failed to load data.json", err));

    const saved = localStorage.getItem('savedArticles');
    if (saved) {
      try {
        setSavedUrls(new Set(JSON.parse(saved)));
      } catch (e) {
        console.error("Failed to parse saved articles", e);
      }
    }
  }, []);

  const toggleSave = (article: Article) => {
    setSavedUrls((prev: Set<string>) => {
      const next = new Set(prev);
      if (next.has(article.url)) {
        next.delete(article.url);
      } else {
        next.add(article.url);
      }
      localStorage.setItem('savedArticles', JSON.stringify(Array.from(next)));
      return next;
    });
  };

  const isSaved = (url: string) => savedUrls.has(url);

  if (!data) {
    return <div className="loading">NOW LOADING...</div>;
  }

  // Filter by recent (24 hours)
  const isRecent = (isoString: string) => {
    if (!isoString) return false;
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return false;
      const diffHours = (new Date().getTime() - d.getTime()) / (1000 * 60 * 60);
      return diffHours >= 0 && diffHours <= 24;
    } catch {
      return false;
    }
  };

  // Filter articles list
  const filteredArticles = recentOnly
    ? data.articles.filter((a: Article) => isRecent(a.published_at))
    : data.articles;

  // Extract Top 10 for Top tab
  const top10 = [...filteredArticles].sort((a, b) => b.normalized_score - a.normalized_score).slice(0, 10);

  // Categorize
  const getTabArticles = () => {
    switch (activeTab) {
      case 'Top':
        return top10;
      case 'あとで読む':
        return filteredArticles.filter((a: Article) => savedUrls.has(a.url));
      default:
        return filteredArticles.filter((a: Article) => a.source.includes(activeTab));
    }
  };

  const tabs = ['Top', 'Zenn', 'Qiita', 'Hatebu', 'HackerNews', 'ObsidianMD', 'ffxiv', 'あとで読む'];

  /**
   * 日付をカード右上バッジ用にフォーマット
   * - 1時間未満: "XX分前"
   * - 24時間未満: "XX時間前"
   * - それ以上:   "YYYY/MM/DD HH:MM"
   */
  const formatDateBadge = (isoString: string): string => {
    if (!isoString) return '日付不明';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return '日付不明';
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMins = Math.floor(diffMs / (1000 * 60));
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

      if (diffMins < 60 && diffMins >= 0) {
        return `${diffMins}分前`;
      } else if (diffHours < 24 && diffHours >= 0) {
        return `${diffHours}時間前`;
      }

      const y = d.getFullYear();
      const mo = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${y}/${mo}/${dd} ${hh}:${mm}`;
    } catch {
      return '日付不明';
    }
  };

  const generatedAt = (() => {
    try {
      const d = new Date(data.generated_at);
      return d.toLocaleString('ja-JP');
    } catch {
      return data.generated_at;
    }
  })();

  return (
    <div className="app-container">
      {/* ===== HEADER ===== */}
      <header className="app-header">
        <h1>★ TECH NEWS DIGEST ★</h1>
        <div className="header-subtitle">- DAILY QUEST BOARD -</div>
        <div className="meta-info">LAST UPDATE: {generatedAt}</div>
        <div className="header-corners">
          <span>◆</span>
          <span>◆</span>
        </div>
      </header>

      {/* ===== FILTER ===== */}
      <div className="filter-controls">
        <label className="toggle-container">
          <input
            type="checkbox"
            checked={recentOnly}
            onChange={(e) => setRecentOnly(e.target.checked)}
          />
          <span>直近24時間のみ</span>
        </label>
      </div>

      {/* ===== TABS ===== */}
      <nav className="tab-navigation">
        {tabs.map(tab => (
          <button
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>

      {/* ===== ARTICLE LIST ===== */}
      <main className="article-list">
        {getTabArticles().length === 0 ? (
          <div className="empty-state">記事がありません</div>
        ) : (
          getTabArticles().map((article, idx) => (
            <article
              key={idx}
              className={`article-card ${article.is_boosted ? 'boosted' : ''}`}
              style={{ animationDelay: `${idx * 0.04}s` }}
            >
              {/* Card Header: source / boost / score / DATE */}
              <div className="card-header">
                <span className={`source-badge ${article.source.split(':')[0].toLowerCase()}`}>
                  {article.source}
                </span>
                {article.is_boosted && <span className="boost-badge">★ BOOST</span>}
                <span className="score-badge">Lv.{Math.round(article.normalized_score)}</span>
                {/* 日付バッジ（右上） */}
                <span className="date-badge">{formatDateBadge(article.published_at)}</span>
              </div>

              {/* Title */}
              <a href={article.url} target="_blank" rel="noopener noreferrer" className="article-title">
                {article.title}
              </a>

              {/* Footer */}
              <div className="card-footer">
                <button
                  className={`save-btn ${isSaved(article.url) ? 'saved' : ''}`}
                  onClick={() => toggleSave(article)}
                >
                  {isSaved(article.url) ? '✓ 保存済み' : '► あとで読む'}
                </button>
              </div>
            </article>
          ))
        )}
      </main>
    </div>
  );
}

export default App
