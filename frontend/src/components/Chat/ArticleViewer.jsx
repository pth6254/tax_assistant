import { useEffect, useState } from 'react'
import { fetchLawArticle } from '../../api/lawApi'

export default function ArticleViewer({ lawName, articleNo, onClose }) {
  const [article, setArticle] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setArticle(null)

    fetchLawArticle(lawName, articleNo)
      .then(data => { if (!cancelled) setArticle(data) })
      .catch(err => { if (!cancelled) setError(err?.detail || '조문을 불러오지 못했습니다.') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [lawName, articleNo])

  return (
    <aside style={{
      width: 380, flexShrink: 0,
      borderLeft: '1px solid var(--border)',
      background: 'var(--surface)',
      display: 'flex', flexDirection: 'column',
      animation: 'slideUp .2s ease',
    }}>
      <header style={{
        padding: '16px 20px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, color: 'var(--text)' }}>
          📖 조문 원문
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none', border: 'none', color: 'var(--text-muted)',
            fontSize: 18, cursor: 'pointer', lineHeight: 1, padding: 4,
          }}
          aria-label="닫기"
        >
          ✕
        </button>
      </header>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>불러오는 중...</div>
        )}

        {error && (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.6 }}>
            ⚠️ {error}
            <div style={{ marginTop: 8 }}>
              ({lawName} {articleNo}은(는) 검색 DB에 저장되어 있지 않거나, AI가 잘못 인용했을 수 있습니다.)
            </div>
          </div>
        )}

        {article && (
          <>
            <div style={{ fontSize: 12, color: 'var(--accent2)', marginBottom: 6 }}>
              {article.law_name} {article.law_type && `(${article.law_type})`}
            </div>
            <h2 style={{
              fontFamily: 'var(--font-serif)', fontSize: 18,
              color: 'var(--text)', fontWeight: 400, marginBottom: 16,
            }}>
              {article.article_no} {article.article_title && `[${article.article_title}]`}
            </h2>
            <div style={{
              fontSize: 14, lineHeight: 1.85, color: 'var(--text)',
              whiteSpace: 'pre-wrap', marginBottom: 20,
            }}>
              {article.article_text}
            </div>
            <div style={{
              fontSize: 12, color: 'var(--text-muted)',
              borderTop: '1px solid var(--border)', paddingTop: 12,
              display: 'flex', flexDirection: 'column', gap: 4,
            }}>
              {article.effective_date && <div>시행일: {article.effective_date}</div>}
              {article.amendment_date && <div>공포일: {article.amendment_date}</div>}
              {article.source_url && (
                <a
                  href={article.source_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: 'var(--accent2)', marginTop: 6 }}
                >
                  법제처 원문 보기 →
                </a>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  )
}
