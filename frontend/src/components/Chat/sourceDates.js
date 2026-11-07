// How the evidence panel states a source's dates. effective_from is the version the text was taken from;
// in_force_since is when that wording first took effect (current articles only). A dated question is judged
// by the second, so the panel shows it whenever it is earlier, e.g. a 2026-03 sale answered from the
// 2026-07-01 version whose wording has not changed since 2022.
const day = value => {
  const digits = String(value || '').replace(/\D/g, '')
  return digits.length === 8 ? `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}` : String(value || '')
}

export function sourceDates(source) {
  if (!source?.effective_from) return '자료 시행일 미확인'
  const version = day(source.effective_from)
  const since = day(source.in_force_since)
  return since && since < version ? `자료 시행일: ${version} (이 문구는 ${since}부터 같음)` : `자료 시행일: ${version}`
}
