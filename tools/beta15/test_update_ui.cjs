const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/update_ui.js','utf8');
function render(state){let index=0;const values=[state,true,''],ctx={document:{body:{}},Ie:{createPortal:(node,target)=>{assert(target);return node}},N:{useRef:()=>({current:null}),useState:v=>[values[index++]??v,()=>{}],useEffect:()=>{}},o:{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}};vm.createContext(ctx);vm.runInContext(source,ctx);return ctx.AppUpdateButton()}
const downloading=JSON.stringify(render({status:'installing',phase:'downloading',percent:42,current:'old',latest:'new',message:'Téléchargement'}));assert(downloading.includes('42 % de cette étape'));assert(downloading.includes('progress'));assert(downloading.includes('dialog'));
const waiting=JSON.stringify(render({status:'installing',percent:null,current:'old'}));assert(waiting.includes('progress'));assert(!waiting.includes('"value":0'));
const finished=JSON.stringify(render({status:'complete',current:'new',latest:'new',percent:100}));assert(finished.includes('Mise à jour terminée'));assert(finished.includes('OK'));assert(!finished.includes('Installer la mise à jour'));
assert(source.includes("action('dismiss')"));assert(source.includes('window.location.reload()'));
console.log('PASS: modal, per-stage real progress, indeterminate progress, explicit completion and acknowledgement.');
