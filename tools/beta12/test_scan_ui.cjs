const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/web/assets/index-CEFd-v_U.js','utf8');
const component=source.slice(source.indexOf('function ArchiveScanControl('),source.indexOf('function quickFilingReady('));
function render(state){let index=0;const values=[state,'',false],context={N:{useState:value=>[values[index++]??value,()=>{}],useEffect:()=>{}},o:{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}};vm.createContext(context);vm.runInContext(component,context);return context.ArchiveScanControl({onChanged:()=>{}})}
let tree=JSON.stringify(render({running:true,indexed_files:12,total_files:40,processed_files:10,percent:25,scan_errors:0}));assert(tree.includes('10 / 40 fichiers'));assert(tree.includes('25 %'));assert(tree.includes('progress'));
tree=JSON.stringify(render({running:true,indexed_files:12,total_files:null,percent:null,scan_errors:0}));assert(tree.includes('Recherche des fichiers'));assert(!tree.includes('"type":"progress"'));
tree=JSON.stringify(render({running:false,indexed_files:12,scan_message:'Scan incomplet',scan_errors:2}));assert(tree.includes('Scan incomplet'));assert(!tree.includes('"type":"progress"'));
assert(source.includes('o.jsx(WorkspaceGate,{}),o.jsx(ArchiveScanControl,{onChanged})'),'Startup progress must be visible on the document workspace');
console.log('PASS: visible startup control, real file progress, unknown discovery percentage, partial scan message.');
