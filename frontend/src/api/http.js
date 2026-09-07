export function errorMessage(error, fallback = '요청을 완료하지 못했습니다. 다시 시도해 주세요.') {
  if (typeof error?.detail === 'string') return error.detail
  if (typeof error?.detail?.message === 'string') return error.detail.message
  if (Array.isArray(error?.detail)) return '입력값의 형식과 필수 항목을 확인해 주세요.'
  return typeof error?.message === 'string' ? error.message : fallback
}
export async function requestJson(url, options = {}) {
  let response
  try { response = await fetch(url, { credentials: 'include', ...options }) }
  catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('서버에 연결하지 못했습니다. 연결을 확인해 주세요.')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw Object.assign(new Error(response.status === 401 ? '로그인이 필요합니다.' : errorMessage(data)), { status: response.status })
  return data
}
