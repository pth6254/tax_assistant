import { useCallback, useEffect, useRef, useState } from 'react'
import { listDocuments, deleteDocument } from '../api/documentsApi'
import { uploadFile } from '../api/uploadApi'
import { errorMessage } from '../api/http'

export function useDocumentLibrary() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [upload, setUpload] = useState(null)
  const alive = useRef(true), version = useRef(0), uploading = useRef(false)
  const refresh = useCallback(async () => {
    const current = ++version.current
    setLoading(true); setError('')
    try {
      const data = await listDocuments()
      if (!Array.isArray(data)) throw new Error('문서 목록 응답을 확인할 수 없습니다. 다시 조회해 주세요.')
      if (alive.current && current === version.current) setDocuments(data)
    } catch (e) { if (alive.current && current === version.current) setError(errorMessage(e)) }
    finally { if (alive.current && current === version.current) setLoading(false) }
  }, [])
  useEffect(() => { alive.current = true; refresh(); return () => { alive.current = false; ++version.current } }, [refresh])
  const add = async file => {
    if (!file || uploading.current) return
    if (loading || error) { setUpload({ status: 'error', message: '기존 파일의 교체 여부를 확인하려면 문서 목록을 먼저 새로고침해 주세요.' }); return }
    if (!file.name.toLowerCase().endsWith('.pdf')) { setUpload({ status: 'error', message: '텍스트가 포함된 PDF 파일을 선택해 주세요.' }); return }
    // Same-name uploads replace existing chunks on the server. Make that consequence explicit.
    if (documents.some(d => d.filename === file.name) && !window.confirm(`“${file.name}”의 기존 내용을 새 파일로 교체할까요?`)) return
    uploading.current = true
    setUpload({ status: 'loading', message: `${file.name} · 문서를 처리하고 있습니다. 완료 전에는 새 내용을 검색할 수 없습니다.` })
    try {
      await uploadFile(file)
      if (alive.current) { setUpload({ status: 'ok', message: `${file.name} · 저장 완료. 문서 목록에서 검색 준비 상태를 확인하세요.` }); await refresh() }
    } catch (e) { if (alive.current) setUpload({ status: 'error', message: errorMessage(e, '문서 처리에 실패했습니다.') }) }
    finally { uploading.current = false }
  }
  const remove = async filename => {
    await deleteDocument(filename)
    if (alive.current) await refresh()
  }
  return { documents, loading, error, upload, add, remove, refresh }
}
