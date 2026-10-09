import { useEffect, useState, type ReactNode } from 'react';
type State = { supported: boolean; running: boolean; status: string; message: string; pages: number; pdf_available: boolean; session?: string };
type Device = { id: string; name: string; label?: string; windows_default?: boolean };
type Props = { onImportFile: (file: File) => Promise<{ id: number }>; onChanged: () => void; renderDocument: (id: number, onNew: () => void) => ReactNode };
export function ScannerPanel({ onImportFile, onChanged, renderDocument }: Props) {
  const [state, setState] = useState<State | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [selected, setSelected] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [connection, setConnection] = useState<{ available: boolean; message: string } | null>(null);
  const [probing, setProbing] = useState(false);
  const refreshDevices = async () => {
    setLoading(true); setError('');
    try {
      const response = await fetch('/api/v1/scanner/devices', { cache: 'no-store' });
      if (!response.ok) throw Error('Détection des scanners indisponible.');
      const data = await response.json();
      setDevices(data.devices || []); setMessage(data.message || '');
      setSelected(previous => data.devices?.some((d: Device) => d.id === previous) ? previous : data.default_device_id || '');
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const response = await fetch('/api/v1/scanner', { cache: 'no-store' });
        if (!response.ok) throw Error('Le scanner est indisponible.');
        const next = await response.json(); if (active) setState(next);
      } catch (e) { if (active) setError(String(e)); }
    };
    poll(); refreshDevices(); const timer = window.setInterval(poll, 1500);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const command = async (action: string, device = selected) => {
    const response = await fetch('/api/v1/scanner', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(action === 'reset' ? { action } : { action, device }) });
    const next = await response.json(); if (!response.ok) throw Error(next.detail || 'Numérisation impossible.');
    if (action !== 'probe') setState(next); return next;
  };
  const testConnection = async () => {
    if (!selected || state?.running || probing) return;
    setProbing(true); setConnection(null);
    try { setConnection(await command('probe')); }
    catch (e) { setError(String(e)); }
    finally { setProbing(false); }
  };
  useEffect(() => { setConnection(null); }, [selected]);
  const choose = async (device: string) => {
    setSelected(device); setError('');
    if (device) try { await command('select', device); } catch (e) { setError(String(e)); }
  };
  const scan = async () => { setError(''); setConnection(null); try { await command('scan'); } catch (e) { setError(String(e)); } };
  const newInvoice = async () => {
    setError('');
    try { await command('reset'); setDocumentId(null); onChanged(); } catch (e) { setError(String(e)); }
  };
  const send = async () => {
    setSending(true); setError('');
    try {
      const response = await fetch('/api/v1/scanner/pdf', { cache: 'no-store' });
      if (!response.ok) throw Error('Le PDF n’est pas disponible.');
      const file = new File([await response.blob()], `facture-scan-${new Date().toISOString().slice(0, 10)}.pdf`, { type: 'application/pdf' });
      const document = await onImportFile(file);
      if (!Number.isInteger(document.id)) throw Error('Le traitement n’a pas confirmé la facture.');
      setDocumentId(document.id); onChanged();
    } catch (e) { setError(String(e)); }
    finally { setSending(false); }
  };
  return <section className="pilot-pc-inbox pilot-scanner">
    <div className="pilot-page-title"><div><span className="pilot-kicker">NUMÉRISATION</span><h1>Scanner et classer</h1><p>Numérisez la facture, puis vérifiez et classez-la ici.</p></div></div>
    {error && <div className="pilot-alert error" role="alert">{error}</div>}
    {documentId !== null ? <>
      <div className="pilot-pc-actions"><button className="pilot-secondary" onClick={newInvoice}>Scanner la facture suivante</button></div>
      {renderDocument(documentId, newInvoice)}
    </> : <>
      <div className="pilot-scanner-controls">
        <label htmlFor="scanner-device">Scanner à utiliser<select id="scanner-device" value={selected} disabled={state?.running || sending || loading || probing} onChange={e => choose(e.target.value)}>
          <option value="">{loading ? 'Recherche…' : 'Choisir un scanner'}</option>
          {devices.map(device => <option key={device.id} value={device.id}>{device.label || device.name}{device.id === selected ? ' · préféré sur ce poste' : device.windows_default ? ' · défaut Windows' : ''}</option>)}
        </select></label>
        <button className="pilot-secondary" disabled={loading || state?.running || sending || probing} onClick={refreshDevices}>Actualiser</button>
        <button className="pilot-secondary" disabled={!selected || state?.running || sending || probing} onClick={testConnection}>{probing ? 'Test…' : 'Tester la connexion'}</button>
      </div>
      {connection && <p role="status" className={connection.available ? 'pilot-verified' : 'pilot-alert'}>{connection.available ? '✓ Accessible lors du test' : 'Connexion indisponible'} — {connection.message}</p>}
      <p className="pilot-scanner-hint">{message || 'Choisissez le scanner Windows qui fonctionne. DocPilot le gardera pour les prochaines factures.'}</p>
      {!loading && state?.supported && !devices.length && <p>Aucun scanner détecté. Vérifiez la connexion et le pilote WIA du fabricant.</p>}
      <div className="pilot-pc-status" role="status"><strong>{sending ? 'Analyse de la facture…' : state?.message || 'Chargement…'}</strong>{(state?.running || sending) && <progress aria-label={sending ? 'Analyse en cours' : 'Numérisation en cours'} />}{!!state?.pages && <span>{state.pages} page(s)</span>}</div>
      <div className="pilot-pc-actions">
        <button className="pilot-primary" disabled={!state?.supported || !selected || state?.running || sending || probing} onClick={scan}>{state?.running ? 'Numérisation…' : state?.pages ? 'Ajouter une page' : 'Numériser la facture'}</button>
        {state?.pdf_available && <button className="pilot-primary" disabled={state.running || sending || probing} onClick={send}>{sending ? 'Analyse…' : 'Analyser et classer ici'}</button>}
        {!!state?.pages && <button className="pilot-secondary" disabled={state?.running || sending} onClick={newInvoice}>Nouvelle facture</button>}
      </div>
      {state?.pdf_available && <iframe title="Facture numérisée" src={'/api/v1/scanner/pdf?pages=' + state.pages + '&session=' + encodeURIComponent(state.session || '') + '#toolbar=0&navpanes=0&view=FitH'} className="pilot-scanner-preview" />}
      <p className="pilot-scanner-hint">Le PDF apparaît ici après la numérisation. Ajoutez les pages d’une même facture avant de lancer son analyse. La numérisation reste locale.</p>
    </>}
  </section>;
}
