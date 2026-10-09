const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync(__dirname+'/scanner_ui.js','utf8').replace('export function','function');
const state={supported:true,running:false,status:'ready',message:'PDF ready',pages:2,pdf_available:true,session:'second-scan'};
function render(id=null){let i=0;const values=[state,[{id:'test',name:'Kyocera MA3500cix',label:'MA3500 · USB'}],'test','','',false,false,id,null,false];const context={encodeURIComponent,N:{useState:v=>[values[i++]??v,()=>{}],useEffect:()=>{}},o:{Fragment:'fragment',jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}};vm.createContext(context);vm.runInContext(code,context);return context.ScannerPanel({onImportFile:()=>{},onChanged:()=>{},renderDocument:id=>({reviewDocument:id})})}
let output=JSON.stringify(render());assert(output.includes('MA3500 · USB')&&output.includes('Ajouter une page')&&output.includes('Analyser et classer ici')&&output.includes('iframe')&&output.includes('second-scan'));
state.running=true;output=JSON.stringify(render());assert(output.includes('progress'));
state.running=false;output=JSON.stringify(render(42));assert(output.includes('"reviewDocument":42')&&output.includes('Scanner la facture suivante'));
assert(!code.includes('onOpen('));
state.supported=false;state.pages=0;state.pdf_available=false;output=JSON.stringify(render());assert(output.includes('"disabled":true'));
console.log('PASS: distinct scanner connections, PDF preview, inline document review and no navigation out of Scanner.');
