function InlineDestination({doc,onChanged,simulation}){
 const [proposal,setProposal]=N.useState(null),[path,setPath]=N.useState(""),[busy,setBusy]=N.useState(false),[error,setError]=N.useState("");
 async function load(){
  try{const response=await fetch(`/api/v1/documents/${doc.id}/quick-filing`);const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:"Dossier inaccessible");setProposal(data);setPath(data.path);setError("")}catch(e){setError(e.message)}
 }
 N.useEffect(()=>{load()},[doc.id,doc.proposed_path,doc.proposed_filename,doc.legal_entity_id,doc.creditor_id,doc.invoice_date,doc.amount_minor,doc.currency]);
 const kind=archiveDocumentInfo(doc).document_type||"invoice";
 const ready=!!doc.legal_entity_id&&!!doc.creditor_id&&!doc.error_message&&!!doc.proposed_filename&&(!archiveMonetary(kind)||(!!doc.invoice_date&&doc.amount_minor!=null&&!!doc.currency));
 async function confirm(){
  if(busy||!proposal)return;setBusy(true);setError("");
  try{const response=await fetch(`/api/v1/documents/${doc.id}/quick-filing`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path,expected:proposal.expected,confirmed:true})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:data.detail?.message||"Classement impossible");await onChanged()}
  catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return o.jsxs("div",{className:"pilot-inline-destination",children:[
  o.jsxs("label",{children:["Dossier proposé · modifiable ici",o.jsx("input",{value:path,disabled:busy||!proposal,"aria-label":"Dossier de classement pour "+doc.original_filename,onChange:e=>setPath(e.target.value),placeholder:"Chargement de la proposition…"})]}),
  proposal&&o.jsx("small",{children:proposal.root+" / "+path}),
  proposal&&o.jsx("small",{children:!proposal.exists||path!==proposal.path?"Le dossier sera créé si nécessaire après votre validation.":"Dossier existant dans l’archive."}),
  !ready&&o.jsx("small",{children:"Des informations de la facture restent à compléter."}),
  o.jsx("button",{className:"pilot-primary",disabled:busy||!ready||!proposal||!path.trim(),onClick:confirm,children:busy?"Classement…":simulation?"Valider en simulation":"Valider ce dossier et classer"}),
  error&&o.jsxs("p",{className:"pilot-alert error",role:"alert",children:[error,o.jsx("button",{className:"pilot-secondary",disabled:busy,onClick:load,children:"Actualiser la proposition"})]})
 ]});
}
