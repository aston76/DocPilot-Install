import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type Candidate = { id: string; path: string; sha: string; kind: string; status: string; matches: string[]; doc_id: number | null; verified: boolean };
type Inbox = { running: boolean; phase: string; visited: number; found: number; errors: number; message: string; items: Candidate[]; total: number; offset: number; limit: number };
type Props = { onImportFile: (file: File) => Promise<{ id: number }>; onOpen: (id: number) => void; onChanged: () => void };
const labels: Record<string,string> = { duplicate: "Copie identique sur le NAS", processed: "Déjà traitée dans DocPilot", imported: "Déjà ajoutée à DocPilot", to_process: "À traiter" };

export function PcInboxPanel({ onImportFile, onOpen, onChanged }: Props) {
  const [state,setState]=useState<Inbox|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState<string|null>(null);
  const [remove,setRemove]=useState<{item:Candidate;deleteFile:boolean}|null>(null);
  const [offset,setOffset]=useState(0);
  const [filter,setFilter]=useState("all");
  const refresh=async()=>{
    const response=await fetch(`/api/v1/pc-inbox?offset=${offset}&filter=${filter}`,{cache:"no-store"});
    if(!response.ok)throw new Error("La recherche locale est indisponible.");
    setState(await response.json());
  };
  useEffect(()=>{
    let active=true;
    const poll=async()=>{try{
      const response=await fetch(`/api/v1/pc-inbox?offset=${offset}&filter=${filter}`,{cache:"no-store"});
      if(!response.ok)throw new Error("Le serveur ne répond pas.");
      const next=await response.json();if(active)setState(next);
    }catch(e){if(active)setError(e instanceof Error?e.message:String(e))}};
    poll();const timer=window.setInterval(poll,3000);
    return()=>{active=false;window.clearInterval(timer)};
  },[offset,filter]);
  const command=async(action:string)=>{
    setError("");
    try{
      const response=await fetch('/api/v1/pc-inbox',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
      const next=await response.json();if(!response.ok)throw new Error(next.detail||"Recherche impossible");
      setState(next);setOffset(0);setFilter('all');
    }catch(e){setError(e instanceof Error?e.message:String(e))}
  };
  const importFile=async(item:Candidate)=>{
    setBusy(item.id);setError("");
    try{
      const response=await fetch(`/api/v1/pc-inbox/${item.id}/file`);
      if(!response.ok){const detail=await response.json();throw new Error(detail.detail||"Le fichier n’est plus accessible.")}
      const blob=await response.blob();
      const filename=item.path.split(/[\\/]/).pop()||'document.pdf';
      const document=await onImportFile(new File([blob],filename,{type:blob.type}));
      await fetch(`/api/v1/pc-inbox/${item.id}/refresh`,{method:'POST'});
      await refresh();onChanged();onOpen(document.id);
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(null)}
  };
  const confirmRemove=async()=>{
    if(!remove)return;
    setBusy(remove.item.id);setError("");
    try{
      const response=await fetch(`/api/v1/pc-inbox/${remove.item.id}/remove`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(remove.deleteFile?{delete_file:true,confirm:true}:{delete_file:false})});
      const next=await response.json();if(!response.ok)throw new Error(next.detail||"Suppression impossible");
      setRemove(null);await refresh();
    }catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(null)}
  };
  return <section className="pilot-pc-inbox">
    <div className="pilot-page-title"><div><span className="pilot-kicker">RECHERCHE LOCALE</span><h1>Factures à traiter sur ce PC</h1><p>Retrouvez les factures oubliées sur cet ordinateur.</p></div><button className="pilot-primary" disabled={state?.running||!!busy} onClick={()=>command('scan')}>{state?.running?'Recherche en cours…':'Détecter les factures sur ce PC'}</button></div>
    <p>Les dossiers Synology, les lecteurs réseau, les archives configurées et les dossiers système sont exclus. Aucun fichier n’est déplacé ou supprimé pendant la recherche.</p>
    {error&&<div className="pilot-alert error" role="alert">{error}<button onClick={()=>setError('')} aria-label="Fermer">×</button></div>}
    <div className="pilot-pc-status" role="status" aria-live="polite"><strong>{state?.message||'Chargement…'}</strong>{state?.running&&<><progress aria-label="Recherche des factures"/><span>{state.visited} fichiers parcourus · {state.found} candidats</span><button className="pilot-secondary" onClick={()=>command('cancel')}>Arrêter la recherche</button></>}{!!state?.errors&&<span>{state.errors} accès ou fichier(s) non vérifiés : résultat partiel.</span>}</div>
    <div className="pilot-filters">{[['all','Tous'],['to_process','À traiter'],['duplicates','Déjà traités / doublons']].map(([value,label])=><button key={value} className={filter===value?'active':''} onClick={()=>{setFilter(value);setOffset(0)}}>{label}</button>)}</div>
    <div className="pilot-pc-list">{state?.items.map(item=><article className="pilot-pc-row" key={item.id}>
      <div className="pilot-pc-description"><strong>{item.path.split(/[\\/]/).pop()}</strong><span>{item.path}</span><span className={'pilot-pc-label '+(item.status==='duplicate'?'duplicate':'')}>{labels[item.status]||item.status}{item.status==='to_process'&&item.kind==='possible'?' · Nature à confirmer':''}</span>{item.matches.length>0&&<small>Correspondance NAS : {item.matches.join(' · ')}</small>}{item.status==='to_process'&&!item.verified&&<small>Vérification du NAS incomplète : l’absence de doublon n’est pas confirmée.</small>}</div>
      <div className="pilot-pc-actions">
        {item.status==='to_process'&&<button className="pilot-primary" disabled={!!busy} onClick={()=>importFile(item)}>{busy===item.id?'Import en cours…':'Importer et traiter'}</button>}
        {item.doc_id!==null&&<button className="pilot-secondary" onClick={()=>onOpen(item.doc_id!)}>Ouvrir dans DocPilot</button>}
        <button className="pilot-secondary" disabled={!!busy} onClick={()=>setRemove({item,deleteFile:false})}>Retirer de la liste</button>
        <button className="pilot-danger" disabled={!!busy} onClick={()=>setRemove({item,deleteFile:true})}>Supprimer aussi du PC</button>
      </div>
    </article>)}</div>
    {state&&!state.items.length&&<p className="pilot-simple-empty">{state.running?'La recherche continue…':'Aucun document dans cette liste. Lancez la détection pour commencer.'}</p>}
    {!!state?.total&&<div className="pilot-pc-pagination"><span>{offset+1}–{Math.min(offset+state.items.length,state.total)} sur {state.total}</span><button className="pilot-secondary" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-100))}>Précédent</button><button className="pilot-secondary" disabled={offset+100>=state.total} onClick={()=>setOffset(offset+100)}>Suivant</button></div>}
    <p><small>Les PDF avec texte sont reconnus par leur contenu ou leur nom. Les photos, scans et documents Office incertains restent à confirmer. Les fichiers uniquement en ligne et ceux dépassant 100 Mo ne sont pas lus.</small></p>
    {remove&&createPortal(<div className="pilot-modal-backdrop pilot-update-backdrop"><div className="pilot-modal pilot-update-modal" role="dialog" aria-modal="true" aria-labelledby="pc-remove-title">
      <h2 id="pc-remove-title">{remove.deleteFile?'Supprimer le fichier de ce PC ?':'Retirer uniquement de la liste ?'}</h2>
      <p className="pilot-modal-filename">{remove.item.path}</p>
      <p>{remove.deleteFile?'Le fichier original sera définitivement supprimé de cet ordinateur. La copie du NAS ne sera pas modifiée.':'Le fichier restera sur cet ordinateur. Cette entrée sera masquée dans la liste.'}</p>
      {error&&<p role="alert">{error}</p>}
      <div className="pilot-modal-actions"><button className="pilot-secondary" disabled={!!busy} onClick={()=>setRemove(null)}>Annuler</button><button className={remove.deleteFile?'pilot-danger':'pilot-primary'} disabled={!!busy} onClick={confirmRemove}>{busy?'Traitement…':remove.deleteFile?'Confirmer la suppression du PC':'Retirer de la liste'}</button></div>
    </div></div>,document.body)}
  </section>;
}
