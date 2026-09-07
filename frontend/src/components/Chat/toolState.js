export const TOOL_LABELS = {
  none: '도구 선택', law_lookup: '법령 원문 조회', document_search: '내 문서 검색',
  income_tax: '소득세 계산', capital_gains: '양도소득세 계산', inheritance: '상속세 계산',
  gift: '증여세 계산', vat: '부가가치세 계산', penalty_tax: '가산세 계산',
}
export const STATUS_LABELS = {
  selecting: '선택 중', running: '실행 중', ok: '완료', not_found: '자료 없음',
  needs_input: '추가 정보 필요', selection_error: '선택 실패',
  invalid_arguments: '입력 확인 필요', timeout: '시간 초과', error: '실행 실패',
  interrupted: '연결 중단',
}
export const isPendingTool = tool => ['selecting', 'running'].includes(tool.status)
export function mergeTool(tools = [], event) {
  if (!TOOL_LABELS[event.tool] || !STATUS_LABELS[event.status]) return tools
  const next = tools.filter(t => t.id !== event.id)
  return [...next, event]
}
export function interruptTools(tools = []) {
  return tools.map(t => isPendingTool(t) ? { ...t, status: 'interrupted' } : t)
}
