export default function ResultCard({ result, onAskAboutResult }) {
  if (!result) return null
  const won = n => Number(n).toLocaleString('ko-KR') + '원'
  return <section className="result-card">
    <div className="result-heading"><h2>{result.tax_type} 계산 결과</h2><span className="unit-label">결과 단위: 원</span></div>
    <div className="final-amount"><span>{result.final_tax < 0 ? '환급세액' : '최종 납부세액'}</span><strong>{won(Math.abs(result.final_tax))}</strong></div>
    <dl className="result-summary"><div><dt>과세표준</dt><dd>{won(result.taxable_income)}</dd></div><div><dt>산출세액</dt><dd>{won(result.calculated_tax)}</dd></div><div><dt>실효세율</dt><dd>{(result.effective_rate * 100).toFixed(2)}%</dd></div></dl>
    <h3>계산 과정</h3><div className="table-scroll"><table><thead><tr><th>항목</th><th>금액</th></tr></thead><tbody>{result.steps.map((s, i) => <tr key={i}><td>{s.label}</td><td>{won(s.amount)}</td></tr>)}</tbody></table></div>
    <div className="basis-info"><h3>적용 기준 확인</h3><p>조회 기준일: {result.basis?.queried_on || '정보 없음'}</p><p>사용한 DB 자료의 시행일: {result.basis?.effective_dates?.join(', ') || '확인 정보 없음'}</p><p className="small muted">서로 다른 시행일의 자료와 구현 상수가 함께 사용될 수 있습니다. 세법의 최신성을 보증하는 표시는 아닙니다.</p></div>
    {!!result.source_articles?.length && <div className="result-sources"><h3>계산 근거</h3>{result.source_articles.map((s, i) => <p key={i}>{s}</p>)}</div>}
    {onAskAboutResult && <button className="button secondary" onClick={onAskAboutResult}>이 결과에 대해 챗봇에게 질문하기</button>}
  </section>
}
