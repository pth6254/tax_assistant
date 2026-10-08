import { test } from 'node:test'
import assert from 'node:assert/strict'
import { issueLabel, sharedSubject } from '../src/components/Chat/issueLabel.js'

const issue = (id, subject, law, kind = 'analysis') => ({ id, subject, law, kind })

test('a subject shared by every analysis issue is not repeated in each label', () => {
  const issues = [issue('1', '복식부기의무자', '소득세법'), issue('2', '복식부기의무자', '국세기본법')]
  assert.equal(sharedSubject(issues), '복식부기의무자')
  assert.deepEqual(issues.map(item => issueLabel(item, issues)), ['소득세법', '국세기본법'])
})

test('different subjects, a single issue and empty subjects keep the existing labels', () => {
  const pair = [issue('1', 'A', '법인세법'), issue('2', 'B', '법인세법')]
  assert.deepEqual(pair.map(item => issueLabel(item, pair)), ['A회사 · 법인세법', 'B회사 · 법인세법'])
  const single = [issue('1', '복식부기의무자', '소득세법')]
  assert.equal(issueLabel(single[0], single), '복식부기의무자 · 소득세법')
  const bare = [issue('1', '', '소득세법'), issue('2', '', '국세기본법')]
  assert.equal(sharedSubject(bare), '')
  assert.deepEqual(bare.map(item => issueLabel(item, bare)), ['소득세법', '국세기본법'])
  assert.equal(issueLabel(issue('1', '', 'ALL'), []), '확인 사항')
})

test('tool issues do not decide whether the analysis subject is shared', () => {
  const issues = [issue('1', '납세자', '소득세법'), issue('2', '납세자', '국세기본법'),
    issue('3', '', 'ALL', 'exact_lookup')]
  assert.equal(sharedSubject(issues), '납세자')
})
