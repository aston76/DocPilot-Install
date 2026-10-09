import { useEffect, useRef, useState, type ReactNode } from 'react';
type State = { supported: boolean; running: boolean; status: string; message: string; pages: number; pdf_available: boolean; session?: string; preview_available?: boolean; preview_kind?: string; preview_version?: number };
type Device = { id: string; name: string; label?: string; windows_default?: boolean; backend?: string; approved?: boolean };
type Imported = { id: number; status?: string; confidence?: Record<string, { detail?: string }> | null };
type Props = { onImportFile: (file: File) => Promise<Imported>; onChanged: () => void; renderDocument: (id: number, onNew: () => void) => ReactNode };
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
  const [capturedUrl, setCapturedUrl] = useState('');
  const [duplicate, setDuplicate] = useState(false);
  const [commandBusy, setCommandBusy] = useState(false);
  const requests = useRef({ sequence: 0, pending: false });
  const captured = useRef('');
  useEffect(() => () => { if (captured.current) URL.revokeObjectURL(captured.current); }, []);
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
    let polling = false;
    const poll = async () => {
      if (polling || requests.current.pending) return;
      polling = true;
      const sequence = ++requests.current.sequence;
      try {
        const response = await fetch('/api/v1/scanner', { cache: 'no-store' });
        if (!response.ok) throw Error('Le scanner est indisponible.');
        const next = await response.json(); if (active && sequence === requests.current.sequence) setState(next);
      } catch (e) { if (active && sequence === requests.current.sequence) setError(String(e)); }
      finally { polling = false; }
    };
    poll(); refreshDevices(); const timer = window.setInterval(poll, 1500);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const command = async (action: string, device = selected) => {
    if (requests.current.pending) throw Error('Une commande du scanner est déjà en cours.');
    requests.current.pending = true; setCommandBusy(true);
    const sequence = ++requests.current.sequence;
    try {
    const response = await fetch('/api/v1/scanner', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(action === 'reset' ? { action } : { action, device }) });
    const next = await response.json(); if (!response.ok) throw Error(next.detail || 'Numérisation impossible.');
    if (action !== 'probe' && sequence === requests.current.sequence) setState(next); return next;
    } finally { requests.current.pending = false; setCommandBusy(false); }
  };
  const testConnection = async () => {
    if (!selected || state?.running || probing) return;
    setProbing(true); setConnection(null);
    try { setConnection(await command('probe')); }
    catch (e) { setError(String(e)); }
    finally { setProbing(false); }
  };
  const approveApi = async () => {
    if (!selected || busy) return;
    setProbing(true); setError('');
    try {
      const configure = async (body: Record<string,string>) => {
        const response = await fetch('/api/v1/scanner/escl', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const result = await response.json();
        if (!response.ok) throw Error(result.detail || 'Configuration API impossible.');
        return result;
      };
      const certificate = await configure({action:'certificate',device:selected});
      if (!window.confirm('Approuver ce scanner pour DocPilot sur ce poste ?\n\n'+certificate.subject+'\nSHA256 : '+certificate.sha256+'\nValide jusqu’au : '+certificate.valid_until+'\n\nLe certificat ne sera pas ajouté à Windows. Refusez si ce scanner ne correspond pas à celui attendu.')) return;
      const result = await configure({action:'approve',token:certificate.token});
      await refreshDevices(); setSelected(result.device);
      setConnection(null); setMessage('Certificat approuvé. Testez la connexion avant de numériser.');
    } catch (e) { setError(String(e)); }
    finally {setProbing(false);}
  };
  useEffect(() => { setConnection(null); }, [selected]);
  const choose = async (device: string) => {
    setSelected(device); setError('');
    if (device) try { await command('select', device); } catch (e) { setError(String(e)); }
  };
  const scan = async () => {
    setError(''); setConnection(null);
    try {
      await command('scan');
      if (captured.current) URL.revokeObjectURL(captured.current);
      captured.current = ''; setCapturedUrl('');
    } catch (e) { setError(String(e)); }
  };
  const newInvoice = async () => {
    setError('');
    try {
      await command('reset'); setDocumentId(null); setDuplicate(false);
      if (captured.current) URL.revokeObjectURL(captured.current);
      captured.current = ''; setCapturedUrl(''); onChanged();
    } catch (e) { setError(String(e)); }
  };
  const send = async () => {
    setSending(true); setError('');
    try {
      const response = await fetch('/api/v1/scanner/pdf', { cache: 'no-store' });
      if (!response.ok) throw Error('Le PDF n’est pas disponible.');
      const blob = await response.blob();
      if (captured.current) URL.revokeObjectURL(captured.current);
      captured.current = URL.createObjectURL(blob); setCapturedUrl(captured.current);
      const file = new File([blob], `facture-scan-${new Date().toISOString().slice(0, 10)}.pdf`, { type: 'application/pdf' });
      const document = await onImportFile(file);
      if (!Number.isInteger(document.id)) throw Error('Le traitement n’a pas confirmé la facture.');
      let matches = false;
      try { matches = !!JSON.parse(document.confidence?.archive_duplicate?.detail || '{}').matches?.length; } catch { /* A malformed hint is not proof of a duplicate. */ }
      setDuplicate(document.status === 'DUPLICATE' || matches);
      setDocumentId(document.id); onChanged();
    } catch (e) { setError(String(e)); }
    finally { setSending(false); }
  };
  const busy = state?.running || sending || probing || commandBusy;
  const previewAvailable = !!capturedUrl || !!(state?.preview_available ?? state?.pdf_available);
  const previewUrl = capturedUrl || '/api/v1/scanner/preview?pages=' + state?.pages + '&version=' + (state?.preview_version || 0) + '&session=' + encodeURIComponent(state?.session || '');
  const preview = previewAvailable && (state?.preview_kind === 'image' && !capturedUrl
    ? <img src={previewUrl} alt="Page reçue du scanner, préparation du PDF" className="pilot-scanner-image" style={{display:"block",maxWidth:"100%",maxHeight:"min(65vh, 560px)",objectFit:"contain",margin:"16px auto"}} />
    : <iframe title="Facture réellement numérisée" src={previewUrl + '#toolbar=0&navpanes=0&view=Fit'} className="pilot-scanner-preview" style={{display:"block",width:"100%",maxWidth:720,minHeight:0,height:"min(65vh, 560px)",margin:"16px auto"}} />);
  return <section className="pilot-pc-inbox pilot-scanner">
    <div className="pilot-page-title"><div><span className="pilot-kicker">NUMÉRISATION</span><h1>Scanner et classer</h1><p>Numérisez la facture, puis vérifiez et classez-la ici.</p></div></div>
    {error && <div className="pilot-alert error" role="alert">{error}</div>}
    {documentId !== null ? <>
      {duplicate && <div className="pilot-alert" role="status"><strong>Document numérisé · doublon détecté</strong><p>L’aperçu ci-dessous montre la page reçue du scanner. Consultez le résultat pour vérifier le doublon ou retirer cette entrée de DocPilot.</p></div>}
      <div className="pilot-pc-actions"><button className="pilot-secondary" disabled={busy} onClick={newInvoice}>{duplicate ? 'Retirer cet aperçu · scanner la suivante' : 'Scanner la facture suivante'}</button></div>
      {previewAvailable && <details className="pilot-scanner-evidence" open={duplicate}><summary>Aperçu de la numérisation reçue</summary>{preview}</details>}
      {renderDocument(documentId, newInvoice)}
    </> : <>
      <div className="pilot-scanner-controls">
        <label htmlFor="scanner-device">Scanner à utiliser<select id="scanner-device" value={selected} disabled={busy || loading} onChange={e => choose(e.target.value)}>
          <option value="">{loading ? 'Recherche…' : 'Choisir un scanner'}</option>
          {devices.map(device => <option key={device.id} value={device.id}>{device.label || device.name}{device.id === selected ? ' · préféré sur ce poste' : device.windows_default ? ' · défaut Windows' : ''}</option>)}
        </select></label>
        <button className="pilot-secondary" disabled={loading || busy} onClick={refreshDevices}>Actualiser</button>
        <button className="pilot-secondary" disabled={!selected || busy} onClick={testConnection}>{probing ? 'Test…' : 'Tester la connexion'}</button>
        {devices.find(d=>d.id===selected)?.backend==='escl' && <button className="pilot-secondary" disabled={busy} onClick={approveApi}>Approuver le scanner API</button>}
      </div>
      {connection && <p role="status" className={connection.available ? 'pilot-verified' : 'pilot-alert'}>{connection.available ? '✓ Accessible lors du test' : 'Connexion indisponible'} — {connection.message}</p>}
      <p className="pilot-scanner-hint">{message || 'Choisissez le scanner Windows qui fonctionne. DocPilot le gardera pour les prochaines factures.'}</p>
      {!loading && state?.supported && !devices.length && <p>Aucun scanner détecté. Vérifiez la connexion et le pilote WIA du fabricant.</p>}
      <div className="pilot-pc-status" role="status"><strong>{sending ? 'Analyse de la facture…' : state?.message || 'Chargement…'}</strong>{(state?.running || sending) && <progress aria-label={sending ? 'Analyse en cours' : 'Numérisation en cours'} />}{!!state?.pages && <span>{state.pages} page(s)</span>}</div>
      <div className="pilot-pc-actions">
        <button className="pilot-primary" disabled={!state?.supported || !selected || busy} onClick={scan}>{state?.running ? 'Numérisation…' : state?.pages ? 'Ajouter une page' : 'Numériser la facture'}</button>
        {state?.pdf_available && <button className="pilot-primary" disabled={busy} onClick={send}>{sending ? 'Analyse…' : 'Analyser et classer ici'}</button>}
        {previewAvailable && <button className="pilot-secondary" disabled={busy} onClick={newInvoice}>Retirer l’aperçu · nouvelle facture</button>}
      </div>
      {preview}
      <p className="pilot-scanner-hint">L’aperçu apparaît dès réception de la page et reste visible pendant l’ajout des suivantes. La détection des doublons commence avec « Analyser et classer ici ». Retirer l’aperçu ne supprime aucun fichier du PC ou du NAS.</p>
    </>}
  </section>;
}
