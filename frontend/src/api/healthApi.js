export async function getDependencyHealth() {
  const response = await fetch('/api/health/dependencies', {
    credentials: 'include',
  })
  if (!response.ok) throw new Error('AI 서비스 상태를 확인하지 못했습니다.')
  return response.json()
}
