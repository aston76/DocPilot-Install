"""Explicit WIA acquisition on Windows; images and PDFs stay on this computer."""
import json,os,subprocess,threading,uuid,shutil
from pathlib import Path
_lock=threading.RLock()
_state={'running':False,'status':'idle','message':'Choisissez un scanner puis numérisez votre facture.','pages':0,'session':None}
_SCRIPT=r'''
param([string]$InputPath)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$config=Get-Content -LiteralPath $InputPath -Raw -Encoding UTF8 | ConvertFrom-Json
try {
$manager=New-Object -ComObject WIA.DeviceManager
if($config.action -eq 'list'){
 $defaultName='';try{$defaultName=[string](Get-CimInstance Win32_Printer -Filter 'Default=True' -OperationTimeoutSec 3 | Select-Object -First 1 -ExpandProperty Name)}catch{}
 $devices=@(foreach($info in $manager.DeviceInfos){if([int]$info.Type -eq 1){
  $name='Scanner';$port='';$description=''
  foreach($property in $info.Properties){
   if($property.Name -eq 'Name'){$name=[string]$property.Value}
   if($property.Name -eq 'Port' -or $property.PropertyID -eq 6){$port=[string]$property.Value}
   if($property.Name -eq 'Description'){$description=[string]$property.Value}
  }
  @{id=[string]$info.DeviceID;name=$name;connection=$port;description=$description;windows_default=($defaultName -ne '' -and $name -eq $defaultName)}
 }})
 ConvertTo-Json -InputObject @{devices=$devices} -Compress;exit 0
}
$info=@($manager.DeviceInfos | Where-Object {$_.DeviceID -eq $config.device}) | Select-Object -First 1
if(-not $info){throw 'Scanner absent ou déconnecté.'}
$device=$null
for($attempt=0;$attempt -lt 2;$attempt++){
 try{$device=$info.Connect();break}
 catch{if($attempt -eq 1){throw};Start-Sleep -Seconds 2}
}
if($config.action -eq 'probe'){ConvertTo-Json -InputObject @{available=$true;message='Connexion au scanner réussie.'} -Compress;exit 0}
$item=$device.Items.Item(1)
foreach($property in $item.Properties){
 if($property.PropertyID -eq 6146){$property.Value=2}
 if($property.PropertyID -eq 6147 -or $property.PropertyID -eq 6148){try{$property.Value=300}catch{}}
}
$dialog=New-Object -ComObject WIA.CommonDialog
$image=$dialog.ShowTransfer($item,'{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}',$true)
if($null -eq $image){ConvertTo-Json -InputObject @{cancelled=$true} -Compress;exit 0}
$image.SaveFile([string]$config.output)
$dpi=300;foreach($property in $item.Properties){if($property.PropertyID -eq 6147){$dpi=[int]$property.Value}}
ConvertTo-Json -InputObject @{cancelled=$false;dpi=$dpi} -Compress
} catch {
 $exception=$_.Exception
 while($exception.InnerException){$exception=$exception.InnerException}
 $code='0x'+$exception.HResult.ToString('X8')
 ConvertTo-Json -InputObject @{error=$true;code=$code} -Compress
}
'''

def driver_error(code):
 messages={
  '0x80210005':'Scanner hors ligne. Réveillez-le depuis son panneau et vérifiez la connexion choisie.',
  '0x8021000A':'Le pilote ne communique pas avec le scanner. Vérifiez le réseau ou le câble, puis la connexion choisie.',
  '0x80210006':'Scanner occupé. Attendez la fin de l’autre tâche puis réessayez.',
  '0x8021000D':'Scanner utilisé par une autre application. Fermez-la puis réessayez.',
  '0x80210007':'Scanner en cours de préchauffage. Attendez quelques instants puis réessayez.',
  '0x80210003':'Aucune feuille dans le chargeur. Placez la facture puis réessayez.',
  '0x80210002':'Bourrage papier. Dégagez le papier avant de réessayer.',
  '0x80210016':'Capot du scanner ouvert. Fermez-le puis réessayez.',
  '0x80210017':'Lampe du scanner éteinte. Réveillez l’appareil puis réessayez.',
 }
 normalized=str(code).lower()
 message=next((value for key,value in messages.items() if key.lower()==normalized),'Le pilote a interrompu la numérisation. Vérifiez le scanner puis réessayez.')
 return message+' Code pilote : '+(str(code) if len(str(code))<=16 else 'inconnu')

def supported():return os.name=='nt'
def data_dir():
 from app.core.config import get_settings
 return Path(get_settings().data_dir)/'scanner'

def bridge(action,folder,device=None):
 folder.mkdir(parents=True,exist_ok=True)
 script=folder/'acquire.ps1';script.write_text(_SCRIPT,encoding='utf-8-sig')
 request=folder/'request.json';request.write_text(json.dumps({'action':action,'device':device,'output':str(folder/'page.png')}),encoding='utf-8')
 env=dict(os.environ)
 # Frozen applications can supply a module path unsuitable for Windows PowerShell.
 system=env.get('SystemRoot',r'C:\Windows')
 env['PSModulePath']=str(Path(system)/'System32'/'WindowsPowerShell'/'v1.0'/'Modules')
 try:
  result=subprocess.run(['powershell.exe','-STA','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-InputPath',str(request)],env=env,capture_output=True,timeout=300 if action=='scan' else 20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 except subprocess.TimeoutExpired:raise ValueError('Le scanner ne répond plus. Vérifiez le scanner puis réessayez.') from None
 if result.returncode:raise ValueError('Scanner inaccessible ou numérisation interrompue. Vérifiez son pilote Windows, sa connexion et le papier.')
 try:value=json.loads(result.stdout.decode('utf-8-sig').strip())
 except (ValueError,UnicodeError):raise ValueError('Réponse du scanner invalide. Réessayez.') from None
 if not isinstance(value,dict):raise ValueError('Réponse du scanner invalide. Réessayez.')
 if value.get('error'):raise ValueError(driver_error(value.get('code','inconnu')))
 return value

def preference():
 try:
  value=json.loads((data_dir()/'preferences.json').read_text(encoding='utf-8'))
  return value if isinstance(value,dict) else {}
 except (OSError,ValueError):return {}

def remember(device):
 if not isinstance(device,str) or not device.strip() or len(device)>1024:raise ValueError('Choisissez un scanner.')
 with _lock:
  folder=data_dir();folder.mkdir(parents=True,exist_ok=True)
  staged=folder/('preferences-'+uuid.uuid4().hex+'.tmp')
  try:
   staged.write_text(json.dumps({'default_device_id':device}),encoding='utf-8')
   staged.replace(folder/'preferences.json')
  finally:staged.unlink(missing_ok=True)

def normalize_devices(items):
 unique={}
 for item in items:
  if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id']:continue
  unique.setdefault(item['id'],dict(item,available=None))
 devices=list(unique.values())
 devices.sort(key=lambda d:(str(d.get('name','')).casefold(),d['id']))
 counts={}
 for device in devices:counts[device.get('name','Scanner')]=counts.get(device.get('name','Scanner'),0)+1
 ordinals={}
 for device in devices:
  name=device.get('name','Scanner')
  ordinals[name]=ordinals.get(name,0)+1
  suffix=str(device.get('connection') or device['id'][-12:])
  device['label']=name+(' · '+suffix+' · connexion '+str(ordinals[name]) if counts[name]>1 else '')
 preferred=preference().get('default_device_id')
 if preferred not in unique:
  defaults=[device['id'] for device in devices if device.get('windows_default')]
  preferred=defaults[0] if len(defaults)==1 else (devices[0]['id'] if len(devices)==1 else None)
 devices.sort(key=lambda d:d['id']!=preferred)
 return devices,preferred

def devices():
 if not supported():return {'supported':False,'devices':[],'default_device_id':None,'message':'La numérisation intégrée est disponible sur Windows avec un pilote WIA. Sur ce Mac, importez le document depuis votre logiciel de scanner.'}
 folder=data_dir()/('discovery-'+uuid.uuid4().hex)
 try:
  items,preferred=normalize_devices(bridge('list',folder).get('devices',[]))
  return {'devices':items,'default_device_id':preferred,'supported':True,'message':'Le scanner choisi est mémorisé sur ce poste. Les connexions portant le même nom sont distinguées.'}
 except (ValueError,OSError) as error:return {'supported':True,'devices':[],'default_device_id':None,'message':str(error)}
 finally:shutil.rmtree(folder,ignore_errors=True)

def probe(device):
 if not supported():raise ValueError('Numérisation intégrée disponible uniquement sur Windows.')
 if not isinstance(device,str) or not device.strip() or len(device)>1024:raise ValueError('Choisissez un scanner.')
 with _lock:
  if _state['running'] or _state.get('probing'):raise ValueError('Le scanner est déjà occupé.')
  _state['probing']=True
 folder=data_dir()/('probe-'+uuid.uuid4().hex)
 try:return dict(bridge('probe',folder,device),device=device)
 except (ValueError,OSError) as error:return {'device':device,'available':False,'message':str(error)}
 finally:
  shutil.rmtree(folder,ignore_errors=True)
  with _lock:_state['probing']=False

def snapshot():
 with _lock:
  folder=data_dir()/(_state['session'] or 'none')
  pdf=(folder/'facture.pdf').is_file()
  image=(folder/'preview.jpg').is_file()
  kind='image' if image and (_state.get('preview_pending') or not pdf) else 'pdf'
  return dict(_state,supported=supported(),pdf_available=pdf,preview_available=pdf or image,preview_kind=kind)

def reset():
 with _lock:
  if _state['running']:raise ValueError('Attendez la fin de la numérisation avant de recommencer.')
  if _state['session']:shutil.rmtree(data_dir()/_state['session'],ignore_errors=True)
  _state.update(status='idle',message='Prêt pour une nouvelle facture.',pages=0,session=None,preview_version=0,preview_pending=False)

def worker(device):
 folder=None
 try:
  with _lock:
   session=_state['session'] or uuid.uuid4().hex
   folder=data_dir()/session;folder.mkdir(parents=True,exist_ok=True)
   _state['session']=session
  page=folder/'page.png';page.unlink(missing_ok=True)
  warning=None
  try:result=bridge('scan',folder,device)
  except (ValueError,OSError) as error:
   if not page.is_file() or not page.stat().st_size:raise
   # A driver may fail reading metadata after SaveFile. The valid image, not
   # its final status, proves acquisition. Decode it before keeping anything.
   warning=str(error);result={'dpi':300}
  if result.get('cancelled') and not (page.is_file() and page.stat().st_size):
   with _lock:
    pages=_state['pages']
    _state.update(status='ready' if pages else 'empty',message=f'Aucune nouvelle page reçue du scanner. Les {pages} page(s) de l’aperçu sont conservées.' if pages else 'Aucune page reçue du scanner. Vérifiez le papier et la connexion, puis réessayez.')
   return
  if not page.is_file() or page.stat().st_size>100*1024*1024:raise ValueError('Image absente ou trop volumineuse.')
  import pymupdf
  pix=pymupdf.Pixmap(page.read_bytes())
  if pix.alpha:pix=pymupdf.Pixmap(pix,0)
  if pix.n>3:pix=pymupdf.Pixmap(pymupdf.csRGB,pix)
  jpeg=pix.tobytes('jpeg',jpg_quality=85);width,height=pix.width,pix.height
  staged_preview=folder/'preview.tmp';staged_preview.write_bytes(jpeg)
  with _lock:
   staged_preview.replace(folder/'preview.jpg')
   _state.update(status='preparing',message='Page reçue. Préparation du PDF…',preview_pending=True,preview_version=_state.get('preview_version',0)+1)
  dpi=result.get('dpi',300)
  if not isinstance(dpi,(int,float)) or not 50<=dpi<=1200:dpi=300
  existing=folder/'facture.pdf'
  pdf=pymupdf.open(existing) if existing.is_file() else pymupdf.open()
  try:
   if len(pdf)>=50:raise ValueError('Limite de 50 pages atteinte. Envoyez cette facture avant de continuer.')
   sheet=pdf.new_page(width=width*72/dpi,height=height*72/dpi);sheet.insert_image(sheet.rect,stream=jpeg)
   output=pdf.tobytes(garbage=4,deflate=True);pages=len(pdf)
  finally:pdf.close()
  if len(output)>50*1024*1024:raise ValueError('PDF trop volumineux : maximum 50 Mo. Les pages précédentes sont conservées.')
  staged=folder/'new.pdf';staged.write_bytes(output)
  with _lock:staged.replace(existing)
  try:remember(device)
  except OSError:pass
  with _lock:_state.update(status='ready',message='Page reçue et PDF prêt. Le pilote a ensuite signalé : '+warning if warning else 'Facture numérisée. Ajoutez une page ou classez-la ici.',pages=pages,session=session,preview_pending=False)
 except (ValueError,OSError,RuntimeError) as error:
  with _lock:_state.update(status='error',message=str(error))
 except Exception:
  with _lock:_state.update(status='error',message='Numérisation impossible. Vérifiez le scanner puis réessayez.')
 finally:
  if folder:
   try:(folder/'page.png').unlink(missing_ok=True)
   except OSError:pass
   with _lock:
    keep=(folder/'facture.pdf').is_file() or (folder/'preview.jpg').is_file()
    if not keep:_state.update(session=None)
   if not keep:shutil.rmtree(folder,ignore_errors=True)
  with _lock:_state['running']=False

def start(device):
 if not supported():raise ValueError('Numérisation intégrée disponible uniquement sur Windows.')
 if not isinstance(device,str) or not device.strip() or len(device)>1024:raise ValueError('Choisissez un scanner.')
 with _lock:
  if _state['running'] or _state.get('probing'):raise ValueError('Le scanner est déjà occupé. Attendez la fin du test ou de la numérisation.')
  _state.update(running=True,status='scanning',preview_pending=False,message='Numérisation en cours. L’aperçu apparaît dès que le scanner transmet la page.')
  threading.Thread(target=worker,args=(device,),daemon=True,name='invoice-scanner').start()

def install(app):
 from fastapi import APIRouter,HTTPException,Request
 from fastapi.responses import Response
 router=APIRouter()
 @app.middleware('http')
 async def preserve_acquisition(request:Request,call_next):
  if request.method=='POST' and request.url.path=='/api/v1/system/quit':
   with _lock:busy=_state['running']
   if busy:
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':'Numérisation en cours : attendez sa fin avant de fermer ou mettre à jour DocPilot.'},status_code=409)
  return await call_next(request)
 def local(request):
  if request.client and request.client.host not in ('127.0.0.1','::1','testclient'):raise HTTPException(403,'Accès local uniquement')
  if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'Origine refusée')
  origin=request.headers.get('origin')
  if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:3005','http://localhost:3005'):raise HTTPException(403,'Origine refusée')
 @router.get('/api/v1/scanner/devices')
 def listing(request:Request):local(request);return devices()
 @router.get('/api/v1/scanner')
 def status(request:Request):local(request);return snapshot()
 @router.post('/api/v1/scanner')
 async def action(request:Request):
  local(request)
  try:body=await request.json()
  except ValueError:raise HTTPException(422,'Demande invalide')
  try:
   if body=={'action':'reset'}:reset()
   elif isinstance(body,dict) and set(body)=={'action','device'} and body['action']=='select':remember(body['device'])
   elif isinstance(body,dict) and set(body)=={'action','device'} and body['action']=='probe':return probe(body['device'])
   elif isinstance(body,dict) and set(body)=={'action','device'} and body['action']=='scan':
    try:
     import docpilot_update
     if docpilot_update._state.get('status')=='installing':raise HTTPException(423,'Mise à jour en cours. Numérisez après la relance.')
    except ImportError:pass
    start(body['device'])
   else:raise HTTPException(422,'Action invalide')
  except ValueError as error:raise HTTPException(409,str(error))
  return snapshot()
 @router.get('/api/v1/scanner/pdf')
 def pdf(request:Request):
  local(request)
  with _lock:
   if _state['running']:raise HTTPException(409,'Attendez la fin de la numérisation.')
   path=data_dir()/(_state['session'] or 'none')/'facture.pdf'
   if not path.is_file():raise HTTPException(404,'Aucune facture numérisée.')
   return Response(path.read_bytes(),media_type='application/pdf',headers={'Cache-Control':'no-store','Content-Disposition':'inline; filename="facture-scan.pdf"'})
 @router.get('/api/v1/scanner/preview')
 def preview(request:Request):
  local(request)
  with _lock:
   state=snapshot()
   if not state['preview_available']:raise HTTPException(404,'Aucune page reçue du scanner.')
   path=data_dir()/state['session']/('preview.jpg' if state['preview_kind']=='image' else 'facture.pdf')
   # Capture stable bytes while holding the commit lock: Windows readers never
   # keep the file open while acquisition replaces it.
   return Response(path.read_bytes(),media_type='image/jpeg' if state['preview_kind']=='image' else 'application/pdf',headers={'Cache-Control':'no-store','Content-Disposition':'inline'})
 app.router.routes[0:0]=router.routes
