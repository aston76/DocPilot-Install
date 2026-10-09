"""Two PCs use different local paths but share relative destination hints."""
import importlib.util, os, shutil, sys, tempfile, types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import docpilot_hash_store as store
import docpilot_startup_sha as sha
spec=importlib.util.spec_from_file_location('docpilot_workspace',Path(__file__).parent.parent/'beta11/docpilot_workspace.py')
w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)
cleared=[]
sys.modules['app.api']=types.SimpleNamespace(documents=types.SimpleNamespace(_archive=types.SimpleNamespace(_workspace_clear_catalogue=lambda:cleared.append(True))))
directory_updates=[]
sys.modules['docpilot_catalogue_directory']=types.SimpleNamespace(update_from_catalogue=lambda catalogue:directory_updates.append(catalogue))
with tempfile.TemporaryDirectory() as temporary:
    base=Path(temporary);os.environ['LOCALAPPDATA']=str(base/'local2')
    roots=[]
    for pc in ('pc1','pc2'):
        root=base/pc/'Example'/w.LEAF
        (root/'Factures').mkdir(parents=True);(root/'Contrats').mkdir();roots.append(root)
    source,target=roots
    supplier='Nouveau Domaine'
    relative='Factures/'+supplier
    (source/relative/'2026').mkdir(parents=True)
    entry={'path':relative,'category':'Factures','supplier':supplier,'filename_label':'Facture Domaine','aliases':['Domaine NV'],'layout':'year'}
    catalogue={'root':str(source),'company':'Example','entries':[entry]}
    store.publish(source,{'files':{}},base/'local1',catalogue)
    def copy_snapshots():
        shutil.copytree(source/'DocPilot-Partage',target/'DocPilot-Partage',dirs_exist_ok=True)
    copy_snapshots()
    payload=next((target/'DocPilot-Partage/v1').glob('*.json')).read_text()
    assert str(source) not in payload,'Never export another PCs absolute path'
    program=base/'program';program.mkdir();w.program_dir=lambda:program
    w.save_catalogue({'root':str(target),'company':'Example','entries':[]})
    sha.refresh_catalogue(target,force=True)
    assert w.read_catalogue()['entries']==[],'Do not offer a not-yet-synchronized destination'
    assert sha.record(target)['catalogue_pending']==1
    (target/relative/'2026').mkdir(parents=True)
    sha.refresh_catalogue(target,force=True)
    local=w.read_catalogue();found=local['entries'][0]
    assert local['root']==str(target) and found['path']==relative
    assert found['filename_label']=='Facture Domaine' and 'Domaine NV' in found['aliases'] and found['layout']=='year'
    assert sha.record(target)['catalogue_pending']==0 and cleared
    assert directory_updates[-1]['entries'][0]['supplier']==supplier
    found['filename_label']='Mon nom personnalisé';w.save_catalogue(local)
    sha.refresh_catalogue(target,force=True)
    assert w.read_catalogue()['entries'][0]['filename_label']=='Mon nom personnalisé','Do not overwrite local customization'
    invalid=dict(entry,path='../../outside')
    assert store.clean_entry(invalid) is None
    store.publish(source,{'files':{}},base/'foreign',dict(catalogue,company='Other',entries=[dict(entry,filename_label='Wrong company')]))
    copy_snapshots()
    entries,errors=store.shared_catalogue(target,'Example')
    assert all(e['filename_label']!='Wrong company' for e in entries) and not errors
    assert 'next_scan=time.monotonic()+300' in Path(sha.__file__).read_text()
print('PASS: two different PC roots, shared relative destinations, deferred folders, imported names/aliases/year layout, preserved local names, company isolation and five-minute reconciliation.')
