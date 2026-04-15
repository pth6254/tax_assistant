import { useState } from 'react'
import FileUpload from './FileUpload'

export default function Sidebar({ user, onLogout }) {
  const [files, setFiles] = useState([])

  const handleUploaded = (file) => {
    setFiles(prev => [...prev, file])
  }

  return (
    <aside style={{
      width: 280, flexShrink: 0,
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      padding: '24px 0',
    }}>
      <div style={{
        fontFamily: 'var(--font-serif)', fontSize: 18,
        padding: '0 24px 24px',
        borderBottom: '1px solid var(--border)',
      }}>
        세무 <span style={{ color: 'var(--accent2)' }}>AI</span>
      </div>

      <div style={{ padding: '20px 24px 0', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 4 }}>
          문서 업로드
        </div>
        <FileUpload onUploaded={handleUploaded} />
      </div>

      {/* 업로드된 파일 목록 */}
      <div style={{
        flex: 1, overflowY: 'auto',
        padding: '12px 24px 20px',
        display: 'flex', flexDirection: 'column', gap: 6,
        marginTop: 12,
      }}>
        {files.map((f, i) => (
          <div key={i} style={{
            background: 'var(--surface2)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: '9px 12px',
            fontSize: 12, color: 'var(--text-muted)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {f.name}
            </span>
            <span style={{
              fontSize: 10,
              background: 'rgba(79,124,255,.15)',
              color: 'var(--accent2)',
              padding: '2px 7px', borderRadius: 99, whiteSpace: 'nowrap', flexShrink: 0,
            }}>
              {f.lawName || '공통'}
            </span>
          </div>
        ))}
      </div>

      {/* 사용자 정보 */}
      <div style={{
        marginTop: 'auto',
        padding: '16px 24px 0',
        borderTop: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <div style={{
          width: 32, height: 32,
          background: 'var(--accent)',
          borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, color: '#fff', fontWeight: 500, flexShrink: 0,
        }}>
          {(user.email[0] || '?').toUpperCase()}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {user.email}
        </div>
        <button onClick={onLogout} style={{
          background: 'none', border: 'none',
          color: 'var(--text-muted)', fontSize: 11, cursor: 'pointer',
          padding: '4px 8px', borderRadius: 6,
        }}>
          로그아웃
        </button>
      </div>
    </aside>
  )
}
