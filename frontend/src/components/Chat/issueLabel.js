// Label for one planned issue. Same rule as the server's answer headings: when every
// analysis issue of the question has the same subject, the subject only repeats.
export function sharedSubject(issues = []) {
  const analysis = issues.filter(issue => (issue.kind || 'analysis') === 'analysis')
  const subjects = new Set(analysis.map(issue => (issue.subject || '').trim()))
  return analysis.length > 1 && subjects.size === 1 ? [...subjects][0] : ''
}

export function issueLabel(issue, issues = []) {
  const bare = /^[A-Z]$/.test(issue.subject || '') ? `${issue.subject}회사` : issue.subject
  const subject = sharedSubject(issues) && issue.subject === sharedSubject(issues) ? '' : bare
  return [subject, issue.law === 'ALL' ? '확인 사항' : issue.law].filter(Boolean).join(' · ')
}
