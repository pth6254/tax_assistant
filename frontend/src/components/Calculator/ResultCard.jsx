const fmt    = (n) => n?.toLocaleString('ko-KR') + '원'
const fmtPct = (r) => (r * 100).toFixed(2) + '%'

export default function ResultCard({ result, onAskAboutResult }) {
  if (!result) return null

  const isRefund = result.final_tax < 0

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
      animation: 'slideUp .3s ease',
    }}>
      {/* 헤더 */}
      <div style={{
        padding: '14px 20px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 10,
        background: 'rgba(79,124,255,.05)',
      }}>
        <span style={{ fontSize: 16 }}>📊</span>
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 15 }}>
          {result.tax_type} 계산 결과
        </span>
      </div>

      {/* 계산 단계 */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
        <div style={{
          fontSize: 10, color: 'var(--text-muted)',
          letterSpacing: 1, textTransform: 'uppercase',
          marginBottom: 12, fontWeight: 600,
        }}>
          계산 과정
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {result.steps.map((step, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              fontSize: 13,
              padding: '4px 0',
              borderBottom: i < result.steps.length - 1 ? '1px solid rgba(255,255,255,.03)' : 'none',
            }}>
              <span style={{ color: 'var(--text-muted)' }}>{step.label}</span>
              <span style={{
                fontVariantNumeric: 'tabular-nums',
                color: step.amount < 0 ? 'var(--danger)' : 'var(--text)',
                fontWeight: 500,
              }}>
                {step.amount < 0 ? '−' : ''}{Math.abs(step.amount).toLocaleString('ko-KR')}원
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 핵심 결과 */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <ResultRow label="과세표준"  value={fmt(result.taxable_income)} />
        <ResultRow label="산출세액"  value={fmt(result.calculated_tax)} />
        <ResultRow label="실효세율"  value={fmtPct(result.effective_rate)} accent />
      </div>

      {/* 최종 납부세액 */}
      <div style={{
        padding: '18px 20px',
        background: 'linear-gradient(135deg, rgba(79,124,255,.1), rgba(124,79,255,.06))',
        borderBottom: result.source_articles?.length > 0 ? '1px solid var(--border)' : 'none',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 14, color: 'var(--text-muted)' }}>
          {isRefund ? '환급세액' : '최종 납부세액'}
        </span>
        <span style={{
          fontSize: 24, fontWeight: 700,
          color: 'var(--accent2)',
          fontVariantNumeric: 'tabular-nums',
          textShadow: '0 0 20px rgba(124,159,255,.3)',
        }}>
          {fmt(Math.abs(result.final_tax))}
        </span>
      </div>

      {/* 근거 법령 */}
      {result.source_articles?.length > 0 && (
        <div style={{
          padding: '12px 20px',
          display: 'flex', flexWrap: 'wrap', gap: 6,
        }}>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', width: '100%', letterSpacing: .5, textTransform: 'uppercase', marginBottom: 2 }}>
            근거 법령
          </span>
          {result.source_articles.map((a, i) => (
            <span key={i} style={{
              fontSize: 11,
              background: 'rgba(79,124,255,.12)',
              color: 'var(--accent2)',
              border: '1px solid rgba(79,124,255,.2)',
              padding: '3px 9px', borderRadius: 99,
            }}>
              {a}
            </span>
          ))}
        </div>
      )}

      {/* 챗봇으로 질문 이어가기 */}
      {onAskAboutResult && (
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)' }}>
          <button
            onClick={onAskAboutResult}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
              background: 'rgba(79,124,255,.08)',
              border: '1px solid rgba(79,124,255,.25)',
              borderRadius: 9, padding: '9px 14px',
              color: 'var(--accent2)', fontSize: 13, cursor: 'pointer',
              transition: 'background .15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(79,124,255,.16)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(79,124,255,.08)' }}
          >
            💬 이 결과에 대해 챗봇에게 질문하기
          </button>
        </div>
      )}
    </div>
  )
}

function ResultRow({ label, value, accent }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, alignItems: 'center' }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{
        color: accent ? 'var(--accent2)' : 'var(--text)',
        fontVariantNumeric: 'tabular-nums',
        fontWeight: accent ? 600 : 400,
      }}>
        {value}
      </span>
    </div>
  )
}
