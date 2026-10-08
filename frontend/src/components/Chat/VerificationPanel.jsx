import { issueLabel } from './issueLabel.js'

const CHECKS = {
  citation: { checked: '인용 내용과 확보한 원문을 대조했습니다.', failed: '인용 근거를 확인하지 못했습니다.',
    not_assessed: '공식 법령 인용 검사를 수행하지 않았습니다.' },
  calculation: { checked: '답변의 최종 금액이 계산기 결과와 일치합니다.', failed: '최종 금액이 계산기 결과와 다릅니다.',
    not_applicable: '계산기를 사용하지 않았습니다.' },
}

const PROGRESS = { planning: '질문의 요청과 쟁점을 확인하고 있습니다…', retrieving: '쟁점별 근거를 찾고 있습니다…',
  generating: '확보한 근거로 답변을 작성하고 있습니다…', checking: '답변의 근거와 조건을 대조하고 있습니다…' }

const STATES = { checked: '근거 대조', limited: '일부 확인 필요', withheld: '답변 보류',
  not_assessed: '검토 범위 미확인' }

function FormulaDetails({ calculation }) {
  if (!calculation?.execution) return null
  const { plan, execution } = calculation
  const labels = Object.fromEntries([...(plan?.values || []), ...(plan?.steps || [])].map(item => [item.id, item.label]))
  const operations = { add: '+', subtract: '−', multiply: '×', divide: '÷', min: '최솟값', max: '최댓값', progressive: '구간별 세율', round: '원 단위 처리' }
  return <details className="formula-details">
    <summary>계산에 사용한 값과 산식</summary>
    <p>{plan?.scope}</p>
    <ul>{plan?.values?.map(value => <li key={value.id}>
      {value.label}: {value.value}{value.unit === 'KRW' ? '원' : ''} · {{ user: '사용자 제공', assumption: '예시 가정', law: '원문 수치', constant: '연산 상수' }[value.origin]}
    </li>)}</ul>
    <ol>{execution.steps.map(step => <li key={step.id}>
      {step.label}: {step.args.map(id => labels[id] || id).join(` ${operations[step.op]} `)}
      {step.args.length === 1 ? ` (${operations[step.op]})` : ''} = {step.value}{step.unit === 'KRW' ? '원' : ''}
    </li>)}</ol>
    <p>숫자 연산은 코드로 수행했으며, 법령 적용과 가정은 별도로 확인해야 합니다.</p>
  </details>
}

export default function VerificationPanel({ verification, loading, progress, onCitationClick }) {
  if (loading) return <p className="verification-progress" role="status">{PROGRESS[progress] || PROGRESS.checking}</p>
  if (!verification) return null
  const { status, checks = {}, citations = [], note } = verification
  const title = status === 'withheld' ? '답변 보류 사유' : '근거 및 확인 사항'
  const checkRows = [
    ['인용 근거', CHECKS.citation[checks.citation] || '인용 검사 결과가 없습니다.'],
    ...(checks.calculation && checks.calculation !== 'not_applicable' ?
      [['계산 확인', CHECKS.calculation[checks.calculation] || '계산 검사 결과가 없습니다.']] : []),
    ['법령 적용 범위', checks.legal_application === 'checked' ?
      '모델이 근거와 적용 조건을 대조했습니다. 법적 정확성 보증은 아닙니다.' :
      '사건의 적용 시점과 법적 해석은 확정하지 않았습니다.'],
  ]
  return <details className={'verification-panel ' + (status === 'withheld' ? 'withheld' : '')}>
    <summary><span>{title}</span>
      {citations.length > 0 && <span className="verification-meta">근거 {citations.length}건</span>}
      <span className="verification-state">{STATES[status] || '검토 정보'}</span>
    </summary>
    <div className="verification-content">
      {note && <p>{note}</p>}
      <dl className="verification-checks">{checkRows.map(([label, text]) =>
        <div key={label} className="verification-check"><dt>{label}</dt><dd>{text}</dd></div>)}
      </dl>
      {verification.plan?.issues?.length > 0 && <ul className="verification-issues" aria-label="쟁점별 확인 상태">
        {verification.plan.issues.map(issue => <li key={issue.id}>
          <span>{issueLabel(issue, verification.plan.issues)}</span><span>
          {verification.judge?.missing_issue_ids?.includes(issue.id) ? '설명 보완 필요' :
            verification.claims?.some(c => c.issue_id === issue.id && c.released) ? '근거가 연결된 설명 제공' :
              verification.coverage?.[issue.id]?.calculation ? '계산 결과 제공' : '추가 확인 필요'}</span>
        </li>)}
      </ul>}
      {verification.plan?.missing_inputs?.length > 0 && <p>추가 확인: {verification.plan.missing_inputs.join(', ')}</p>}
      <FormulaDetails calculation={verification.formula_calculation} />
      {Object.entries(verification.formula_calculations || {}).map(([id, report]) =>
        <FormulaDetails key={id} calculation={report.formula_calculation} />)}
      {citations.length > 0 && <div className="verification-sources">
        <strong>대조한 조문</strong>
        {citations.map((source, index) => source.text ? <details key={source.evidence_id || index}>
          <summary>{source.origin === 'user_document' ? '[사용자 문서]' : `[${source.label}]`} {source.law_name || source.source} {source.reference} — 사용한 원문</summary>
          <p>{source.effective_from ? `자료 시행일: ${source.effective_from}` : '자료 시행일 미확인'} {source.location}</p>
          <pre tabIndex={0} aria-label="답변에 사용한 원문" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{source.text}</pre>
        </details> : <button key={`${source.law_name}-${source.reference}-${index}`}
          type="button" onClick={() => onCitationClick?.(source.law_name, source.reference)}>
          [{source.label}] {source.law_name} {source.reference} 원문 열기
        </button>)}
      </div>}
    </div>
  </details>
}
