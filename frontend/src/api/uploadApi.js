export const uploadFile = async (file) => {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch('/api/upload', {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  const data = await res.json()
  if (!res.ok) throw data
  return data
}
