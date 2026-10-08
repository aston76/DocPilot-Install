"""Observable processing and actionable validation states, without guessed progress."""
import asyncio
import inspect
import threading
import time
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

_current = ContextVar('docpilot_processing', default=None)
_lock = threading.RLock()
_jobs = {}
STAGES = {'reading':'Lecture du PDF et OCR', 'ai':'Lecture par ChatGPT', 'checks':'Vérification des informations et des doublons', 'filing':'Copie du fichier', 'verification':'Contrôle d’intégrité du fichier copié', 'starting':'Préparation'}

def stage(name):
    job = _current.get()
    if job:
        with _lock:
            job.update(stage=name, stage_started=time.monotonic())

def job_view(job):
    elapsed = int(time.monotonic()-job['started'])
    stage_seconds = int(time.monotonic()-job['stage_started'])
    return {k:job.get(k) for k in ('id','document_id','filename','stage','active','error')} | {
        'elapsed_seconds':elapsed, 'stage_seconds':stage_seconds,
        'copy_bytes':job.get('copy_bytes'), 'copy_total':job.get('copy_total'),
        'copy_percent':round(100*job['copy_bytes']/job['copy_total'],1) if job.get('copy_total') else None,
        'label':STAGES.get(job['stage'],'Traitement'),
        'slow':job['active'] and stage_seconds>=30,
        'message':('Cette étape dépasse deux minutes. Le traitement peut encore continuer ; ne relancez pas un second classement.' if stage_seconds>=120 else 'Cette étape prend plus de temps que prévu. Le document n’est pas encore classé.') if job['active'] and stage_seconds>=30 else ''}

def validation(doc, archive):
    from docpilot_dates import candidates
    messages = []
    confidence = doc.confidence or {}
    monetary = archive.monetary_kind(archive.info(doc).get('document_type','invoice'))
    fields = [('legal_entity_id','supplier_missing','Fournisseur à confirmer'),('creditor_id','company_missing','Société à confirmer')]
    if monetary:
        fields += [('invoice_date','date_missing','Date d’émission à confirmer'),('amount_minor','amount_missing','Montant à confirmer'),('currency','currency_missing','Devise à confirmer')]
    for attr, code, title in fields:
        if getattr(doc,attr,None) is None or getattr(doc,attr,None)=='':
            if attr=='invoice_date' and confidence.get('invoice_date',{}).get('method')=='document_conflict':
                code,title='date_conflict','Dates contradictoires : correction manuelle requise'
            messages.append({'code':code,'title':title,'action':'Ouvrez Corriger les informations, vérifiez le PDF et enregistrez la valeur. Attendre ne résoudra pas ce blocage.'})
    if doc.error_message:
        text=doc.error_message
        lower=text.lower()
        code = 'ai_connection' if any(w in lower for w in ('chatgpt','connexion','timeout')) else 'filing_error' if 'class' in lower else 'processing_error'
        messages.append({'code':code,'title':text,'action':'Vérifiez la connexion et relancez une seule analyse, ou complétez les champs manuellement.' if code=='ai_connection' else 'Vérifiez le PDF et le dossier de destination avant de réessayer.'})
    if str(doc.status)=='DUPLICATE':
        messages.append({'code':'duplicate','title':'Doublon détecté','action':'Contrôlez le document existant avant de conserver une autre copie.'})
    dates=candidates(doc.extracted_text or '')
    return {'document_id':doc.id,'status':str(doc.status),'needs_action':bool(messages) and str(doc.status) in ('TO_VALIDATE','ERROR','DUPLICATE'),
            'messages':messages,'dates':dates,'waiting_will_help':False}

def install(app):
    from app.api import documents as d
    from fastapi import APIRouter,Depends,HTTPException,Request
    from starlette.concurrency import run_in_threadpool
    import docpilot_chatgpt
    from docpilot_inline_filing import local

    def track(original,path):
        signature=inspect.signature(original)
        def start(args,kwargs):
            bound=signature.bind(*args,**kwargs)
            doc_id=bound.arguments.get('doc_id')
            filename=getattr(bound.arguments.get('file'),'filename',None)
            with _lock:
                if doc_id is not None and any(j['active'] and j['document_id']==doc_id for j in _jobs.values()):
                    raise HTTPException(409,'Un traitement est déjà en cours pour ce document. Consultez son état avant de réessayer.')
                key=str(time.time_ns())
                job={'id':key,'document_id':doc_id,'filename':filename,'active':True,'stage':'filing' if 'filing' in path or 'validate' in path else 'starting','started':time.monotonic(),'stage_started':time.monotonic(),'error':None}
                _jobs[key]=job
                for old in list(_jobs):
                    if len(_jobs)>100 and not _jobs[old]['active']: _jobs.pop(old)
            return job,_current.set(job)
        def finish(job,token,result=None,error=None):
            with _lock:
                job['active']=False
                if result is not None:job['document_id']=getattr(result,'id',job['document_id'])
                if error is not None:job['error']='Traitement interrompu. Vérifiez le document et corrigez les informations si nécessaire.'
            _current.reset(token)
        if inspect.iscoroutinefunction(original):
            @wraps(original)
            async def wrapped(*args,**kwargs):
                job,token=start(args,kwargs)
                try:
                    result=await run_in_threadpool(lambda:asyncio.run(original(*args,**kwargs)))
                    finish(job,token,result=result)
                    return result
                except BaseException as error:
                    finish(job,token,error=error);raise
        else:
            @wraps(original)
            def wrapped(*args,**kwargs):
                job,token=start(args,kwargs)
                try:
                    result=original(*args,**kwargs);finish(job,token,result=result);return result
                except BaseException as error:
                    finish(job,token,error=error);raise
        return wrapped

    for route in app.router.routes:
        if getattr(route,'methods',None) and 'POST' in route.methods and route.path in ('/api/v1/documents/upload','/api/v1/documents/{doc_id}/reanalyze','/api/v1/documents/{doc_id}/quick-filing','/api/v1/documents/{doc_id}/validate'):
            route.dependant.call=track(route.dependant.call,route.path)

    def hook(owner,name,value):
        original=getattr(owner,name)
        @wraps(original)
        def wrapped(*args,**kwargs):
            stage(value)
            return original(*args,**kwargs)
        setattr(owner,name,wrapped)
    hook(d,'extract_pdf','reading')
    hook(docpilot_chatgpt,'analyze_invoice','ai')
    hook(d,'_apply_decision','checks')
    hook(d,'file_document','filing')
    from app.pipeline.act import filing
    original_copy=filing.shutil.copyfile
    @wraps(original_copy)
    def measured_copy(src,dst,*args,**kwargs):
        job=_current.get()
        if not job or not str(dst).endswith('.docpilot-part'):
            return original_copy(src,dst,*args,**kwargs)
        total=Path(src).stat().st_size
        with _lock:job.update(copy_bytes=0,copy_total=total)
        with open(src,'rb') as source,open(dst,'wb') as destination:
            for chunk in iter(lambda:source.read(1024*1024),b''):
                destination.write(chunk)
                with _lock:job['copy_bytes']+=len(chunk)
            destination.flush()
        stage('verification')
        return dst
    filing.shutil.copyfile=measured_copy

    router=APIRouter(dependency_overrides_provider=app)
    @router.get('/api/v1/processing')
    def processing(request:Request):
        local(request)
        with _lock:return {'jobs':[job_view(j) for j in _jobs.values() if j['active'] or time.monotonic()-j['started']<300]}

    @router.get('/api/v1/documents/{doc_id}/diagnostics')
    def diagnostic(doc_id:int,request:Request,session=Depends(d.get_session)):
        local(request)
        doc=session.get(d.Document,doc_id)
        if not doc:raise HTTPException(404,'Document introuvable')
        info=validation(doc,d._archive)
        with _lock:
            recent=next((job_view(j) for j in reversed(list(_jobs.values())) if j['document_id']==doc_id),None)
            info['job']=recent if recent and recent['active'] else None
            info['last_job']=recent
        if recent and recent['error'] and str(doc.status) in ('TO_VALIDATE','ERROR'):
            info['messages'].append({'code':'request_interrupted','title':recent['error'],'action':'Consultez le PDF et l’état du document avant de réessayer. Aucun nouveau classement ne sera lancé automatiquement.'})
            info['needs_action']=True
        if info['job']:info.update(needs_action=False,waiting_will_help=True)
        return info
    app.router.routes[0:0]=router.routes
