const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/theme_ui.js','utf8').replace('export function','function');
for(const [saved,system,resolved] of [['dark',false,'dark'],['light',true,'light'],['system',true,'dark'],['bad',false,'light']]){
 const element={dataset:{}},store={};let callback;
 const context={localStorage:{getItem:()=>saved,setItem:(k,v)=>store[k]=v},document:{documentElement:element},window:{matchMedia:()=>({matches:system,addEventListener:(e,c)=>callback=c,removeEventListener:()=>{}})},N:{useState:init=>[init(),()=>{}],useEffect:effect=>effect()},o:{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}};
 vm.createContext(context);vm.runInContext(source,context);const node=context.ThemeSwitch();assert(node.props['aria-label']==='Apparence');assert.equal(element.dataset.theme,resolved);assert(store['docpilot-theme']);assert(callback);
}
console.log('PASS: saved dark/light, system preference, persistence and live system listener.');
