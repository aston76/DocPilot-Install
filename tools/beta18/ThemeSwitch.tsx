import { useEffect, useState } from 'react';
type Theme = 'system' | 'light' | 'dark';
export function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(() => {
    try { const saved = localStorage.getItem('docpilot-theme'); return saved === 'light' || saved === 'dark' ? saved : 'system'; } catch { return 'system'; }
  });
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => { document.documentElement.dataset.theme = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme; };
    apply(); try { localStorage.setItem('docpilot-theme', theme); } catch { /* Theme still works when browser storage is unavailable. */ }
    media.addEventListener('change', apply); return () => media.removeEventListener('change', apply);
  }, [theme]);
  return <select className="pilot-theme-switch" aria-label="Apparence" value={theme} onChange={event => setTheme(event.target.value as Theme)}>
    <option value="system">Thème système</option><option value="light">Mode clair</option><option value="dark">Mode sombre</option>
  </select>;
}
