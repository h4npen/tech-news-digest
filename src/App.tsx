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
    return <div className="loading">読み込み中...</div>;
  }

  // Extract Top 10 for Top tab
  const allArticles = data.articles;
  const top10 = [...allArticles].sort((a, b) => b.normalized_score - a.normalized_score).slice(0, 10);
  
  // Categorize
  const getTabArticles = () => {
    switch(activeTab) {
      case 'Top':
        return top10;
      case 'あとで読む':
        return allArticles.filter((a: Article) => savedUrls.has(a.url));
      default:
        // Ex: "Zenn", "Reddit: r/ObsidianMD"
        return allArticles.filter((a: Article) => a.source.includes(activeTab));
    }
  };

  const tabs = ['Top', 'Zenn', 'Qiita', 'Hatebu', 'HackerNews', 'ObsidianMD', 'ffxiv', 'あとで読む'];

  const formatDate = (isoString: string) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch {
      return '';
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Tech News Digest</h1>
        <div className="meta-info">
          Latest Update: {new Date(data.generated_at).toLocaleString()}
        </div>
      </header>

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

      <main className="article-list">
        {getTabArticles().length === 0 ? (
          <div className="empty-state">記事がありません。</div>
        ) : (
          getTabArticles().map((article, idx) => (
            <article key={idx} className={`article-card ${article.is_boosted ? 'boosted' : ''}`}>
              <div className="card-header">
                <span className={`source-badge ${article.source.split(':')[0].toLowerCase()}`}>
                  {article.source}
                </span>
                {article.is_boosted && <span className="boost-badge">★ Boost</span>}
                <span className="score-badge">Score: {article.normalized_score}</span>
              </div>
              <a href={article.url} target="_blank" rel="noopener noreferrer" className="article-title">
                {article.title}
              </a>
              <div className="card-footer">
                <span className="date">{formatDate(article.published_at)}</span>
                <button 
                  className={`save-btn ${isSaved(article.url) ? 'saved' : ''}`}
                  onClick={() => toggleSave(article)}
                >
                  {isSaved(article.url) ? '保存済み' : 'あとで読む'}
                </button>
              </div>
            </article>
          ))
        )}
      </main>
    </div>
  )
}

export default App
