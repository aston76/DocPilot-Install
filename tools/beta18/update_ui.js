function AppUpdateButton(){
 const [state,setState]=N.useState(null),[opened,setOpened]=N.useState(false),[error,setError]=N.useState('');
 const lastStatus=N.useRef(null);
 const active=state?.status==='installing';
 const newer=(current,latest)=>{const key=v=>{const m=/^v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$/.exec(v||'');return m?[+m[1],+m[2],+m[3],m[4]===undefined?1000000:+m[4]]:null};const a=key(current),b=key(latest);if(!a||!b)return false;for(let i=0;i<4;i++){if(a[i]!==b[i])return b[i]>a[i]}return false};
 const available=!!state?.available&&newer(state.current,state.latest)&&state.status==='available';
 const refresh=async()=>{try{
   const r=await fetch('/api/v1/system/update',{cache:'no-store'});if(!r.ok)return;
   const next=await pilotApiJson(r);
   setState(previous=>{if(previous?.current&&previous.current!==next.current){window.location.reload();}return next;});
   setError('');
   if(next.status==='current'&&lastStatus.current==='installing')setOpened(false);
   if(['installing','error'].includes(next.status)&&lastStatus.current!==next.status)setOpened(true);
   lastStatus.current=next.status;
 }catch{setState(previous=>previous?.status==='installing'?{...previous,message:'DocPilot applique la mise à jour en arrière-plan et redémarrera automatiquement. Veuillez patienter…'}:previous)}};
 N.useEffect(()=>{refresh();const timer=setInterval(refresh,1000);return()=>clearInterval(timer)},[]);
 const action=async value=>{setError('');try{const r=await fetch('/api/v1/system/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:value})});const next=await pilotApiJson(r);if(!r.ok)throw Error(next.detail||'Mise à jour indisponible');setState(next);}catch(e){setError(e.message)}};
 const busy=['checking','installing'].includes(state?.status),complete=state?.status==='complete';
 return o.jsxs('div',{className:'pilot-update',children:[
  o.jsx('button',{className:'pilot-update-button',onClick:()=>{setOpened(true);if(!busy&&!complete)action('check')},children:active?'Mise à jour en cours…':available?'Mise à jour disponible':'Mise à jour'}),
  opened&&Ie.createPortal(o.jsx('div',{className:'pilot-modal-backdrop',children:o.jsxs('div',{className:'pilot-modal',role:'dialog','aria-modal':true,'aria-labelledby':'update-title',children:[
   o.jsx('h2',{id:'update-title',children:complete?'Mise à jour terminée':'Mise à jour de DocPilot'}),
   o.jsx('p',{children:state?'Version installée : '+state.current+(available?' · Version disponible : '+state.latest:''):'Vérification…'}),
   o.jsx('p',{role:error?'alert':'status','aria-live':'polite',children:error||state?.message||(available?'Une nouvelle version est disponible.':'Vous avez la dernière version.')}),
   busy&&o.jsx('progress',{max:100,...(Number.isFinite(state?.percent)?{value:state.percent}:{}),'aria-label':'Progression de la mise à jour',style:{width:'100%',height:'20px'}}),
   busy&&Number.isFinite(state?.percent)&&o.jsx('p',{children:state.percent+' % de cette étape'}),
   active&&o.jsx('p',{children:'DocPilot redémarrera automatiquement à la fin de l’installation. Vos données et réglages sont conservés.'}),
   o.jsx('div',{className:'pilot-modal-actions',children:complete?o.jsx('button',{className:'pilot-primary',onClick:()=>{setOpened(false);action('dismiss')},children:'OK'}):o.jsxs('div',{children:[
    !busy&&o.jsx('button',{className:'pilot-secondary',onClick:()=>setOpened(false),children:'Fermer'}),
    !busy&&o.jsx('button',{className:'pilot-primary',onClick:()=>action(available?'install':'check'),children:available?'Installer la mise à jour':'Vérifier de nouveau'})]})})
  ]})}),document.body)
 ]});
}
