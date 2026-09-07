// A small shared outline icon set; no network or icon-font dependency.
const paths = {
  chat: 'M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 0 1 19 0Z',
  book: 'M12 5c-3-2-7-2-10-1v15c3-1 7-1 10 1m0-15c3-2 7-2 10-1v15c-3-1-7-1-10 1V5Z',
  file: 'M14 2H4v20h16V8l-6-6Zm0 0v6h6M8 13h8M8 17h6',
  calculator: 'M5 2h14v20H5V2Zm3 3h8v4H8V5Zm0 8h1m3 0h1m3 0h1M8 17h1m3 0h1m3 0h1',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 22v-3a8 8 0 0 1 16 0v3',
  plus: 'M12 5v14M5 12h14', menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6', send: 'M12 20V4m-7 7 7-7 7 7',
  stop: 'M6 6h12v12H6Z', trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  chevron: 'm9 5 7 7-7 7', down: 'm5 9 7 7 7-7', check: 'm4 12 5 5L20 6',
  refresh: 'M20 8a9 9 0 1 0 0 9M20 2v6h-6', logout: 'M9 3H3v18h6m5-15 6 6-6 6M8 12h12',
}
export default function Icon({ name, size = 20, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}><path d={paths[name] || paths.file} /></svg>
}
