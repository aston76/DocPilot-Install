import { useEffect, useRef, useState } from 'react';
export function CatalogueRecovery({onRefresh}: {onRefresh: () => void}) {
  const [state, setState] = useState<{running:boolean;status:string;message:string}|null>(null);
  const [error, setError] = useState('');
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;
  useEffect(() => {
    let active = true, polling = false, previous = '';
    async function poll() {
      if (polling) return;
      polling = true;
      try {
        const response = await fetch('/api/v1/catalogue-directory', {cache:'no-store'});
        if (!response.ok) throw Error('Récupération des dossiers indisponible.');
        const next = await response.json();
        if (active) {
          setState(next);
          const signature = JSON.stringify(next);
          if (!next.running && ['complete','partial'].includes(next.status) && signature !== previous) refresh.current();
          previous = signature;
        }
      } catch(e) {if(active) setError(String(e));}
      finally {polling=false;}
    }
    poll();const timer=window.setInterval(poll,1500);
    return () => {active=false;window.clearInterval(timer);};
  }, []);
  async function recover() {
    setError('');setState({running:true,status:'reading',message:'Lecture des dossiers…'});
    try {
      const response=await fetch('/api/v1/catalogue-directory',{method:'POST'});
      if(!response.ok) throw Error('Récupération des dossiers indisponible.');
      setState(await response.json());
    } catch(e) {setError(String(e));setState(null);}
  }
  return <div className="pilot-catalogue-recovery">
    <div role="status"><strong>{state?.message || 'La liste comprend tous les noms enregistrés sur ce poste.'}</strong><p>Les noms manquants sont récupérés dans les dossiers de l’archive configurée. Les entrées retirées restent désactivées. Aucun document n’est analysé.</p>{state?.running && <progress aria-label="Récupération des noms" />}</div>
    <button className="pilot-secondary" disabled={state?.running} onClick={recover}>{state?.running ? 'Récupération…' : 'Récupérer les sociétés des dossiers'}</button>
    {error && <p role="alert">{error}</p>}
  </div>;
}
