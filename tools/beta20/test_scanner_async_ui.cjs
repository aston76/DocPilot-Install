const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/scanner_ui.js','utf8').replace('export function','function');
async function main(){
 let states=[{supported:true,running:false,status:'ready',message:'ready',pages:1,pdf_available:true,session:'scan'},[{id:'test',name:'Test'}],'test','','',false,false,null,null,false,'',false,false];
 let si=0,ri=0,ei=0,refs=[],effects=[],timers=[],commands=[],late;
 let getCount=0,uploadFails=false;
 const ctx={encodeURIComponent,URL,File:class extends Blob{constructor(parts,name,options){super(parts,options);this.name=name}},window:{setInterval:fn=>timers.push(fn),clearInterval:()=>{}},fetch:async(url,options={})=>{
  if(url.endsWith('/devices'))return {ok:true,json:async()=>({devices:states[1],default_device_id:'test'})};
  if(url.endsWith('/pdf'))return {ok:true,blob:async()=>new Blob(['%PDF acquired scan'],{type:'application/pdf'})};
  if(options.method==='POST'){
   let {action}=JSON.parse(options.body);commands.push(action);
   return {ok:true,json:async()=>action==='reset'?{supported:true,running:false,pages:0,pdf_available:false,message:'reset'}:{...states[0],running:true,status:'scanning',message:'scanning'}};
  }
  getCount++;
  return new Promise(resolve=>{late=()=>resolve({ok:true,json:async()=>({supported:true,running:false,status:'ready',pages:1,pdf_available:true,message:'stale ready'})})});
 },N:{useState:initial=>{const i=si++;if(states[i]===undefined)states[i]=initial;return [states[i],value=>states[i]=typeof value==='function'?value(states[i]):value]},useRef:initial=>{const i=ri++;return refs[i]??(refs[i]={current:initial})},useEffect:fn=>{const i=ei++;effects[i]??=fn}},o:{Fragment:'fragment',jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 const props={onChanged:()=>{},onImportFile:async()=>{if(uploadFails)throw Error('Analysis failed');return {id:42,status:'DUPLICATE'}},renderDocument:id=>({review:id})};
 function render(){si=ri=ei=0;return ctx.ScannerPanel(props)}
 function find(node,label){if(!node||typeof node!=='object')return null;if(node.type==='button'&&node.props.children===label)return node;for(let child of [].concat(node.props?.children||[])){const found=find(child,label);if(found)return found}return null}
 render();effects.forEach(fn=>fn());await new Promise(r=>setImmediate(r));
 await find(render(),'Ajouter une page').props.onClick();assert(states[0].running);
 late();await new Promise(r=>setImmediate(r));assert(states[0].running&&states[0].message==='scanning','Old poll must not override newer scan command');
 states[0]={supported:true,running:false,pages:1,pdf_available:true,session:'scan'};
 await find(render(),'Analyser et classer ici').props.onClick();let result=JSON.stringify(render());
 assert(states[7]===42&&states[11]===true&&result.includes('blob:')&&result.includes('"open":true'));
 await find(render(),'Retirer cet aperçu · scanner la suivante').props.onClick();assert(states[7]===null&&states[10]===''&&!states[11]);assert(commands.every(action=>['scan','reset'].includes(action)));
 states[0]={supported:true,running:false,pages:1,pdf_available:true,session:'scan'};uploadFails=true;
 await find(render(),'Analyser et classer ici').props.onClick();assert(states[4].includes('Analysis failed')&&states[10].startsWith('blob:'));
 await find(render(),'Ajouter une page').props.onClick();assert(states[10]==='','A new scan must clear the captured PDF from a failed import');
 console.log('PASS: stale polling cannot restore cancelled/ready state, actual scan survives duplicate/import failure, preview-only reset and no stale preview after a new acquisition.');
}
main().catch(error=>{console.error(error);process.exit(1)});
