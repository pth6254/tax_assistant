export const SUPPORTED_DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'hwpx', 'pptx', 'html', 'htm']
export const MAX_DOCUMENT_BYTES = 50 * 1024 * 1024

export function validateDocumentFile(file) {
  if (!file) return '파일을 선택해 주세요.'
  const extension = file.name?.split('.').pop()?.toLowerCase()
  if (!SUPPORTED_DOCUMENT_EXTENSIONS.includes(extension)) {
    return 'PDF, DOCX, HWPX, PPTX, HTML 파일만 업로드할 수 있습니다. 구형 HWP는 지원하지 않습니다.'
  }
  if (file.size === 0) return '빈 파일은 업로드할 수 없습니다.'
  if (file.size > MAX_DOCUMENT_BYTES) return '파일 크기는 50MB 이하여야 합니다.'
  return ''
}
