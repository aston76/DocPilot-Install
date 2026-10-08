const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/workspace_gate.js','utf8');
function harness(info,error=''){
 let index=0;const values=[info,error,false,''];
 const context={N:{useState:initial=>[values[index++]??initial,()=>{}],useEffect:()=>{}},o:{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})},window:{location:{reload:()=>{context.reloaded=true}}},docPilotFetch:async(url,options)=>{context.request={url,options};return {ok:true,json:async()=>({ready:true})}}};
 vm.createContext(context);vm.runInContext(source,context);return context;
}
function flatten(node){if(!node||typeof node!=='object')return [node];return [node,...(Array.isArray(node.props?.children)?node.props.children:[node.props?.children]).flatMap(flatten)]}
(async()=>{
 let context=harness({ready:false,state:'ambiguous',message:'Plusieurs archives correspondent',choices:[{company:'Example',root:'Z:/Example/Fournisseurs-Créanciers'}]});
 let tree=context.WorkspaceGate();assert.equal(tree.props.role,'alert');assert(JSON.stringify(tree).includes('bloqués'));
 const choice=flatten(tree).find(node=>node?.type==='button'&&node.props.children?.startsWith?.('Example'));
 await choice.props.onClick();assert.equal(context.request.url,'/api/v1/workspace/select');assert.equal(JSON.parse(context.request.options.body).root,'Z:/Example/Fournisseurs-Créanciers');assert(context.reloaded);
 context=harness({ready:true,message:'Dossier vérifié : Z:/Example',choices:[]});tree=context.WorkspaceGate();assert.equal(tree.props.role,'status');assert(JSON.stringify(tree).includes('Dossier vérifié'));assert(!JSON.stringify(tree).includes('bloqués'));
 context=harness(null,'Dossier inaccessible');assert(JSON.stringify(context.WorkspaceGate()).includes('Dossier inaccessible'));
 console.log('PASS: blocking startup banner, ambiguous choice, checked default selection and reload, verified status, visible error.');
})().catch(error=>{console.error(error);process.exitCode=1});
