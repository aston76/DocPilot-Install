const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync(__dirname+'/scanner_ui.js','utf8').replace('export function','function');
const state={supported:true,running:false,status:'ready',message:'PDF ready',pages:2,pdf_available:true};
function render(){let i=0;const values=[state,[{id:'test',name:'Kyocera MA3500cix'}],'test','','',false,false];const context={N:{useState:v=>[values[i++]??v,()=>{}],useEffect:()=>{}},o:{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}};vm.createContext(context);vm.runInContext(code,context);return context.ScannerPanel({onImportFile:()=>{},onOpen:()=>{},onChanged:()=>{}})}
let output=JSON.stringify(render());assert(output.includes('Kyocera MA3500cix')&&output.includes('Ajouter une page')&&output.includes('Traiter cette facture')&&output.includes('iframe'));
state.running=true;output=JSON.stringify(render());assert(output.includes('progress')&&!output.includes('iframe'));
state.running=false;state.supported=false;state.pages=0;state.pdf_available=false;output=JSON.stringify(render());assert(output.includes('"disabled":true'));
console.log('PASS: scanner selection, multipage PDF preview, processing action, busy state and unsupported platform');
