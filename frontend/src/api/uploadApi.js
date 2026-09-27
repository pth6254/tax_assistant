export const uploadFile = async (file) => {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch('/api/upload', {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 413) throw { detail: '파일 크기가 업로드 한도를 초과했습니다. (최대 50MB)' }
    throw data
  }
  return data
}
