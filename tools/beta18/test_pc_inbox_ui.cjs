const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/pc_inbox_ui.js','utf8').replace('export function ','function ');
const item={id:'test',path:'C:\\Users\\Example\\Documents\\'+('Nom très long '.repeat(15))+'.pdf',kind:'invoice',status:'duplicate',matches:['Factures/Example/2026/copy.pdf'],doc_id:null,verified:true};
const state={running:false,items:[item],total:1,offset:0,limit:100,message:'Found',errors:0};
function render(remove=null){
 let index=0;const values=[state,'',null,remove,0,'all'];
 const context={N:{useState:v=>[values[index++]??v,()=>{}],useEffect:()=>{}},Ie:{createPortal:(node,target)=>{assert.strictEqual(target,context.document.body);return node}},document:{body:{}},o:{Fragment:"fragment",jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}};
 vm.createContext(context);vm.runInContext(source,context);return context.PcInboxPanel({onImportFile:()=>{},onOpen:()=>{},onChanged:()=>{}});
}
const row=JSON.stringify(render());
assert(row.includes('Vider la liste')&&row.includes('Aucun appel à l’IA'));
assert(row.includes('Retirer de la liste')&&row.includes('Supprimer aussi du PC'));
assert(row.includes('Copie identique sur le NAS'));
assert(!row.includes('Importer et traiter'),'Do not offer import for a verified duplicate');
const listOnly=JSON.stringify(render({item,deleteFile:false}));assert(listOnly.includes('Le fichier restera sur cet ordinateur'));
const physical=JSON.stringify(render({item,deleteFile:true}));assert(physical.includes('Confirmer la suppression du PC')&&physical.includes('définitivement supprimé'));
assert(physical.includes('dialog')&&physical.includes('Annuler'));
item.status='to_process';item.kind='possible';const pending=JSON.stringify(render());assert(pending.includes('Importer et traiter')&&pending.includes('Nature à confirmer'));
console.log('PASS: two distinct removal choices, explicit permanent-file confirmation, centered portal, no duplicate import, uncertain document review and long source names.');

state.running=true;const running=JSON.stringify(render());assert(running.includes('Arrêter la recherche')&&running.includes('fragment'));state.running=false;
console.log('PASS: active scan progress renders without an undefined Fragment.');
