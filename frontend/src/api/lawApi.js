const BASE = '/api/law-articles'

export const fetchLawArticle = async (lawName, articleNo) => {
  const params = new URLSearchParams({ law_name: lawName, article_no: articleNo })
  const res = await fetch(`${BASE}/lookup?${params}`, { credentials: 'include' })
  const data = await res.json()
  if (!res.ok) throw data
  return data
}
