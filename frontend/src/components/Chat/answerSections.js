// Decorate sanitized Markdown blocks. These labels only change presentation;
// the server remains responsible for which statements may be released.
const SECTIONS = {
  '핵심 판단': 'conclusion',
  '판단 근거': 'reasoning',
  '실무 확인 사항': 'practical',
  '추가로 확인할 사항': 'practical',
  '추가 확인이 필요한 부분': 'limits',
  '확인한 근거': 'sources',
}

export function decorateAnswerSections(root) {
  const nodes = [...root.children]
  let section = null
  for (const node of nodes) {
    const name = node.textContent.trim()
    const kind = SECTIONS[name]
    const isHeading = node.tagName === 'H2' || node.tagName === 'H3'
    const isLabel = node.tagName === 'P' && node.childNodes.length === 1 &&
      node.firstElementChild?.tagName === 'STRONG'
    if (isHeading || (kind && isLabel)) {
      section = null
      if (!kind) continue
      section = root.ownerDocument.createElement('section')
      section.className = `answer-section answer-${kind}`
      section.setAttribute('aria-label', name)
      node.replaceWith(section)
      section.append(node)
      node.classList.add('answer-section-title')
    } else if (section) {
      section.append(node)
    }
  }
}
