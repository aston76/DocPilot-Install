"""Verified automatic filing shared by import and reanalysis."""
import inspect
import json
import re
from contextvars import ContextVar
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
from functools import wraps


def supplier_country_currency(text, creditor=None):
    """Infer only from the issuer block, excluding recipient and payment data."""
    header=(text or '')[:1800]
    boundaries=[m.start() for m in re.finditer(r'\b(?:spett\.?le|bill\s+to|invoice\s+to|ship\s+to|lieu\s+de\s+livraison|adresse\s+de\s+livraison)\b',header,re.I)]
    if creditor:
        match=re.search(re.escape(creditor).replace(r'\ ',r'\s+'),header,re.I)
        if match:boundaries.append(match.start())
    if boundaries:
        boundary=min(boundaries)
        column=boundary-(header.rfind('\n',0,boundary)+1)
        # OCR can place the issuer and recipient side by side. Preserve the
        # issuer's left column below the recipient label, never its address.
        left='\n'.join(line[:column] for line in header[boundary:].splitlines()[1:7]) if column>=20 else ''
        header=header[:boundary]+left
    countries={
        'CH':('CHF',r'\b(?:suisse|switzerland|schweiz|svizzera)\b'),
        'LI':('CHF',r'\bliechtenstein\b'),
        'IT':('EUR',r'\b(?:italia|italy|italie)\b'),
        'FR':('EUR',r'\bfrance\b'),
        'DE':('EUR',r'\b(?:deutschland|germany|allemagne)\b'),
        'AT':('EUR',r'\b(?:austria|autriche|österreich)\b'),
        'BE':('EUR',r'\b(?:belgium|belgique|belgië)\b'),
        'ES':('EUR',r'\b(?:spain|espagne|españa)\b'),
        'PT':('EUR',r'\bportugal\b'),
        'NL':('EUR',r'\b(?:netherlands|nederland|pays.bas)\b'),
        'GB':('GBP',r'\b(?:united kingdom|royaume.uni|great britain)\b'),
        'US':('USD',r'\b(?:united states|états.unis|usa)\b'),
        'CA':('CAD',r'\bcanada\b'),
        'AU':('AUD',r'\b(?:australia|australie)\b'),
        'JP':('JPY',r'\b(?:japan|japon)\b'),
    }
    found={code for code,(_,pattern) in countries.items() if re.search(pattern,header,re.I)}
    swiss_vat=bool(re.search(r'\bCHE[- ]?\d{3}[. ]?\d{3}[. ]?\d{3}\b',header,re.I))
    swiss_phone=bool(re.search(r'\+\s*41(?=[\s(]*\d)',header))
    swiss_address=bool(re.search(r'\bCH[- ]?\d{4}\b',header))
    if sum((swiss_vat,swiss_phone,swiss_address))>=2:found.add('CH')
    italian_phone=bool(re.search(r'\+\s*39(?=[\s(]*\d)',header))
    italian_vat=bool(re.search(r'\b(?:P\.?\s*I\.?|IT)\s*(?:e\s*C\.?\s*F\.?)?\s*[:.]?\s*\d{11}\b',header,re.I))
    if italian_phone and italian_vat:found.add('IT')
    if len(found)!=1:return None
    code=next(iter(found))
    return code,countries[code][0]


def service_document(text):
    # Explicit non-wine goods/services only; missing vintages alone prove nothing.
    wine = re.search(r'\b(?:vino|vin|vins|wine|bouteilles?|bottiglie|pinot|turriga|chardonnay|merlot)\b', text, re.I)
    service = re.search(r'\b(?:toners?|cartouches?|imprimante|transfer.belt|drum pack|electricite|electricity|telephonie|honoraires|maintenance informatique)\b', text, re.I)
    return bool(service and not wine)


def dated_text(text):
    from docpilot_dates import invoice_dates
    return invoice_dates(text)


def service_total(text):
    values = set()
    # Swiss invoices state the tax-inclusive base and then the tax component.
    for match in re.finditer(r'TVA\s+incluse\s+\d+[.,]\d+\s*%\s*/\s*(CHF|EUR|USD|GBP)\s+([\d\s\x27’.,]+)\s*:', text, re.I):
        raw = re.sub(r'[\s\x27’]', '', match[2]).replace(',', '.')
        try:
            amount = Decimal(raw)
            if amount > 0 and amount.as_tuple().exponent >= -2:
                values.add((int(amount * 100), match[1].upper()))
        except InvalidOperation:
            pass
    return values


def install(app):
    from app.api import documents as d
    from app.pipeline.decide import heuristics as h
    from sqlalchemy import select
    import docpilot_archive as archive
    from docpilot_inline_filing import safe_path
    from fastapi import APIRouter
    from fastapi.routing import APIRoute
    importing = ContextVar('docpilot_importing', default=False)
    old_setting = d._get_setting
    def setting(session, key, default=None):
        if key == 'auto_classify_enabled' and importing.get():
            return 'false'
        return old_setting(session, key, default)
    d._get_setting = setting
    original_classify = h.classify

    @wraps(original_classify)
    def classify(session, text, layout=None):
        result = original_classify(session, text, layout)
        if getattr(result.confidence.get('ai'), 'method', '') == 'document_ambiguous':
            return result
        if result.amount_minor is None and getattr(result.confidence.get('amount'),'method','') != 'document_conflict':
            amount,currency,raw,certain=h.find_amount(text)
            if certain and amount is not None:
                result.amount_minor=int(amount*100)
                result.amount_raw=raw
                result.currency=result.currency or currency
                result.confidence['amount']=h.FieldConfidence(.90,'explicit_total','Solde explicitement libellé dans le document ; devise à confirmer si absente.')
        dates = dated_text(text)
        if len(dates) > 1:
            result.invoice_date = None
            result.confidence['invoice_date'] = h.FieldConfidence(0., 'document_conflict', 'Plusieurs dates de facture : choisissez la date d’émission dans Corriger les informations. Attendre ou relancer ne valide pas le document.')
        elif dates and not result.invoice_date:
            result.invoice_date = next(iter(dates))
            result.confidence['invoice_date'] = h.FieldConfidence(.96, 'explicit_invoice_date', 'Date d’émission explicitement libellée ; échéance et transport exclus.')
        elif dates and result.invoice_date:
            if dates == {str(result.invoice_date)}:
                result.confidence['invoice_date'] = h.FieldConfidence(.97, 'text_and_ai', 'Date explicitement libellée et confirmée par le texte.')
            else:
                result.invoice_date = None
                result.confidence['invoice_date'] = h.FieldConfidence(0., 'document_conflict', 'Dates contradictoires : vérifier le PDF.')
        if service_document(text):
            values = service_total(text)
            if values and result.amount_minor is not None:
                if values == {(result.amount_minor, result.currency)}:
                    result.confidence['amount'] = h.FieldConfidence(.97, 'text_and_ai', 'Montant TVA incluse et devise confirmés dans le texte.')
                else:
                    result.amount_minor = result.amount_raw = result.currency = None
                    result.confidence['amount'] = h.FieldConfidence(0., 'document_conflict', 'Montant TVA incluse contradictoire ou multiple.')
        result.year=archive.registration_year()
        result.confidence['vintage']=h.FieldConfidence(1.,'registration_year','Année de classement issue de la date d’enregistrement dans DocPilot : '+str(result.year))
        if result.amount_minor is not None and not result.currency and getattr(result.confidence.get('amount'),'method','')!='document_conflict':
            fields=(layout or {}).get('chatgpt_fields') or {}
            inferred=supplier_country_currency(text,fields.get('creditor'))
            if inferred:
                country,currency=inferred
                result.currency=currency
                result.confidence['currency']=h.FieldConfidence(.95,'supplier_country','Devise absente du PDF, déduite du pays du fournisseur selon votre règle : '+country+' → '+currency)
                amount,printed_currency,raw,certain=h.find_amount(text)
                if certain and amount is not None and int(amount*100)==result.amount_minor and printed_currency is None:
                    result.confidence['amount']=h.FieldConfidence(.97,'text_and_country','Solde confirmé dans le document ; devise '+currency+' déduite du pays du fournisseur '+country+'.')
        if result.amount_minor is not None and not result.currency:
            result.confidence['amount']=h.FieldConfidence(.90,'explicit_total','Montant confirmé dans le document ; devise absente à confirmer.')
            result.confidence['currency']=h.FieldConfidence(0.,'country_uncertain','Devise absente et pays du fournisseur incertain : choisissez la devise avant classement.')
        return result

    h.classify = d.classify = classify
    old_refresh = d._refresh_proposal

    def invoice_route(session, doc):
        info = archive.info(doc)
        if info.get('document_type') != 'invoice':
            return None
        if not doc.legal_entity_id or not doc.creditor_id or not archive.catalogue():
            return None
        supplier = session.get(d.LegalEntity, doc.legal_entity_id)
        company = session.get(d.Creditor, doc.creditor_id)
        if not supplier or not supplier.active or not company or not company.active or archive.key(company.name) != archive.key(archive.catalogue()['company']):
            return None
        entry = archive.resolve(supplier.name, 'invoice')
        if entry:
            return entry['path']+'/'+str(archive.year_of_registration(doc.received_at)) if entry.get('layout') != 'irregular' else None
        # Never resolve a catalogue ambiguity by inventing a new folder.
        if any(archive.key(supplier.name) in {archive.key(a) for a in e.get('aliases', [])} for e in archive.catalogue()['entries'] if e['category'] == 'Factures'):
            return None
        if not service_document(doc.extracted_text or '') and (doc.confidence or {}).get('legal_entity',{}).get('score',0)<.95:
            return None
        try:
            return safe_path('Factures/' + supplier.name+'/'+str(archive.year_of_registration(doc.received_at)), 'Factures')
        except Exception:
            return None

    @wraps(old_refresh)
    def refresh(session, doc):
        doc.year=archive.year_of_registration(doc.received_at)
        old_refresh(session, doc)
        route = invoice_route(session, doc)
        if route:
            doc.proposed_path = route
            info = archive.info(doc)
            info.update(route=route, year_policy='registration_year', reason='Fournisseur confirmé : dossier fournisseur et année d’enregistrement.')
            confidence = dict(doc.confidence or {})
            confidence['archive'] = {'score': .97, 'method': 'service_supplier', 'detail': json.dumps(info, ensure_ascii=False)}
            confidence['destination'] = {'score': .97, 'method': 'service_supplier', 'detail': route}
            confidence['vintage'] = {'score': 1., 'method': 'registration_year', 'detail': 'Année d’enregistrement dans DocPilot : '+str(doc.year)}
            doc.confidence = confidence
    d._refresh_proposal = refresh

    old_perform = d._perform_filing

    def duplicates(session, doc):
        source = session.get(d.DocumentSource, doc.id)
        if d._duplicates.lookup(doc.sha256, source.source_sha256 if source else None)['matches']:
            return 'Fichier identique déjà présent dans l’archive.'
        # One invoice can be scanned twice with different binary hashes.
        if doc.invoice_number and doc.legal_entity_id and doc.creditor_id and doc.invoice_date and doc.amount_minor is not None and doc.currency:
            others = session.scalars(select(d.Document).where(d.Document.id != doc.id, d.Document.legal_entity_id == doc.legal_entity_id, d.Document.creditor_id == doc.creditor_id, d.Document.invoice_number == doc.invoice_number, d.Document.invoice_date == doc.invoice_date, d.Document.amount_minor == doc.amount_minor, d.Document.currency == doc.currency, d.Document.status != 'DELETED')).all()
            if any(other.status in ('FILED_AUTO', 'FILED', 'VALIDATED') or other.id < doc.id for other in others):
                return 'Même société, date de facture, numéro et montant dans la même devise : vérifier le doublon.'
        return None

    @wraps(old_perform)
    def perform(session, doc, on_conflict='ask'):
        reason = duplicates(session, doc)
        if reason:
            raise ValueError(reason)
        route = invoice_route(session, doc)
        if route and doc.proposed_path == route:
            root = d._filing_root(session)
            destination = d._safe_destination(root, route)
            if not destination.resolve().is_relative_to(root.resolve()):
                raise ValueError('Destination hors de l’archive.')
            return d._previous_perform_filing(session, doc, on_conflict)
        return old_perform(session, doc, on_conflict)
    d._perform_filing = perform

    def blockers(session, doc):
        reasons = []
        if str(d._get_setting(session, 'auto_classify_enabled', 'false')).lower() != 'true':
            reasons.append('Classement automatique désactivé.')
        if doc.status != 'TO_VALIDATE':
            return reasons + ['Document déjà traité ou doublon.']
        if doc.error_message:
            reasons.append(doc.error_message)
        info = archive.info(doc)
        kind = info.get('document_type')
        monetary = archive.monetary_kind(kind)
        if not archive.category(kind) or kind in ('proforma', 'other'):
            reasons.append('Type de document à confirmer avant classement automatique.')
        if not monetary and archive.local_document_type(doc.extracted_text or '') != kind:
            reasons.append('Type de document à corroborer dans le texte.')
        if not doc.proposed_path:
            reasons.append('Destination à confirmer : fournisseur ou société non reconnu dans cette archive.')
        if not doc.proposed_filename:
            reasons.append('Nom de fichier absent.')
        else:
            from pathlib import Path
            if Path(doc.proposed_filename).name != doc.proposed_filename or '\\' in doc.proposed_filename:
                reasons.append('Nom de fichier invalide.')
        if not all((doc.legal_entity_id, doc.creditor_id)) or (monetary and (not doc.invoice_date or not doc.currency or doc.amount_minor is None)):
            reasons.append('Fournisseur, société, date, montant ou devise incomplet.')
        if monetary and not doc.currency:
            reasons.append('Confirmez la devise : elle est absente du document et le pays du fournisseur ne permet pas de la déterminer sans doute.')
        if archive.catalogue() and doc.creditor_id:
            company = session.get(d.Creditor, doc.creditor_id)
            if not company or not company.active or archive.key(company.name) != archive.key(archive.catalogue()['company']):
                reasons.append('La société ne correspond pas à cette archive.')
        if doc.proposed_path and archive.catalogue() and not (archive.validate_route(doc.proposed_path) or doc.proposed_path == invoice_route(session, doc)):
            reasons.append('Destination non reconnue dans cette archive.')
        try:
            threshold = max(.9, float(d._get_setting(session, 'auto_threshold', '.95')))
        except (TypeError, ValueError):
            threshold = .95
        confidence = doc.confidence or {}
        for field in (('legal_entity', 'creditor', 'invoice_date', 'amount') if monetary else ('legal_entity', 'creditor')):
            if confidence.get(field, {}).get('score', 0.) < threshold:
                reasons.append('Lecture à corroborer : ' + field + '.')
        duplicate = duplicates(session, doc)
        if duplicate:
            reasons.append(duplicate)
        return reasons

    def attempt(session, doc):
        reasons = blockers(session, doc)
        if reasons:
            return False
        try:
            final, digest, verified, replaced = perform(session, doc, 'ask')
            d._mark_filed(session, doc, final, digest, verified, replaced, auto=True)
            session.commit()
            return True
        except Exception as error:
            session.rollback()
            doc.error_message = 'Classement automatique impossible : ' + str(error)
            session.commit()
            return False

    d._auto_blockers = blockers
    d._auto_duplicate_reason = duplicates
    d._attempt_auto_filing = attempt
    old_out = d._to_out
    @wraps(old_out)
    def to_out(session, doc):
        out = old_out(session, doc)
        confidence = dict(out.confidence or {})
        confidence['automatic'] = {'score': 0. if doc.status == 'TO_VALIDATE' else 1., 'method': 'automatic_status', 'detail': json.dumps({'reasons': blockers(session, doc) if doc.status == 'TO_VALIDATE' else []}, ensure_ascii=False)}
        out.confidence = confidence
        return out
    d._to_out = to_out

    # Original import handles filing itself; this shared post-step also supports
    # reanalysis and enforces the configured global threshold consistently.
    for name in ('upload_document', 'reanalyze_document'):
        original = getattr(d, name)
        signature = inspect.signature(original)
        def make_wrapper(fn, sig):
            def finish(args, kwargs, output):
                bound = sig.bind(*args, **kwargs)
                session = bound.arguments['session']
                doc = session.get(d.Document, output.id)
                if doc and doc.status == 'TO_VALIDATE':
                    scope=d._company_context(session,doc) if hasattr(d,'_company_context') else nullcontext()
                    with scope:
                        refresh(session, doc)
                        session.commit()
                        attempt(session, doc)
                        return to_out(session, doc)
                return output
            if inspect.iscoroutinefunction(fn):
                @wraps(fn)
                async def wrapped(*args, **kwargs):
                    token = importing.set(True)
                    try:
                        output = await fn(*args, **kwargs)
                    finally:
                        importing.reset(token)
                    return finish(args, kwargs, output)
            else:
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    return finish(args, kwargs, fn(*args, **kwargs))
            return wrapped
        wrapped = make_wrapper(original, signature)
        setattr(d, name, wrapped)
        for route in d.router.routes:
            if getattr(route, 'endpoint', None) is original:
                route.endpoint = wrapped
                route.dependant.call = wrapped
                # Copy a fresh route before lazy included routers and SPA fallback.
                fresh = APIRoute('/api/v1' + route.path, wrapped,
                    methods=route.methods, response_model=route.response_model,
                    status_code=route.status_code,
                    dependency_overrides_provider=app)
                app.router.routes.insert(0, fresh)

    @app.middleware('http')
    async def fresh_api(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response
