"""Explicit filing from the queue, including a user-confirmed new supplier folder."""
import json
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy.orm import Session

FIELDS = ('proposed_path', 'proposed_filename', 'legal_entity_id', 'creditor_id', 'invoice_date', 'amount_minor', 'currency')

def snapshot(doc):
    return {key: str(value) if key == 'invoice_date' and value else value
            for key in FIELDS for value in [getattr(doc, key, None)]}

def safe_path(value, category):
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(422, 'Choisissez un dossier.')
    value = value.strip()
    parts = value.split('/')
    if len(parts) < 2 or parts[0] != category or any(not p or p in ('.', '..') or
            any(c in p for c in '\\:< >"|?*\x00'.replace(' ', '')) or p.endswith(('.', ' ')) for p in parts):
        raise HTTPException(422, 'Utilisez un chemin relatif dans la catégorie du document.')
    return str(PurePosixPath(value))

def suggestion(doc, archive, supplier):
    info = archive.info(doc)
    category = archive.category(info.get('document_type', 'invoice'))
    if not category or category == 'Douanes':
        return doc.proposed_path or '', category
    if doc.proposed_path:
        return doc.proposed_path, category
    entry = archive.resolve(supplier, info.get('document_type', 'invoice'), subtype=info.get('document_subtype'))
    # Keep a recognised supplier's folder. Do not invent a wine vintage.
    if entry:
        return entry['path'] + ('/' + str(doc.year) if doc.year and category == 'Factures' else ''), category
    name = ''.join(c for c in (supplier or '') if c not in '\\/:<>"|?*\x00').strip(' .')
    return category + '/' + name if name else '', category

def local(request):
    if request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise HTTPException(403, 'Accès local uniquement')
    if request.headers.get('origin') not in (None, 'http://127.0.0.1:8765', 'http://localhost:8765') or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origine refusée')

def install(app, documents=None):
    if documents is None:
        from app.api import documents
    d = documents
    router = APIRouter()

    def context(session, doc_id):
        doc = session.get(d.Document, doc_id)
        if not doc:
            raise HTTPException(404, 'Document introuvable')
        supplier = session.get(d.LegalEntity, doc.legal_entity_id) if doc.legal_entity_id else None
        return doc, supplier

    @router.get('/api/v1/documents/{doc_id}/quick-filing')
    def options(doc_id: int, request: Request, session: Session = Depends(d.get_session)):
        local(request)
        doc, supplier = context(session, doc_id)
        path, category = suggestion(doc, d._archive, supplier.name if supplier else None)
        root = d._filing_root(session)
        return {'path': path, 'category': category, 'root': str(root), 'exists': bool(path and (root / path).is_dir()), 'expected': snapshot(doc)}

    @router.post('/api/v1/documents/{doc_id}/quick-filing')
    def confirm(doc_id: int, request: Request, payload: dict = Body(...), session: Session = Depends(d.get_session)):
        local(request)
        if payload.get('confirmed') is not True:
            raise HTTPException(422, 'Confirmez le dossier proposé.')
        doc, supplier = context(session, doc_id)
        import sys
        updater = sys.modules.get('docpilot_update')
        if updater and updater._state['status'] == 'installing':
            raise HTTPException(423, 'Mise à jour en cours. Attendez le redémarrage.')
        if doc.status != 'TO_VALIDATE' or doc.error_message:
            raise HTTPException(409, 'Ce document ne peut pas être classé dans son état actuel.')
        if payload.get('expected') != snapshot(doc):
            raise HTTPException(409, 'Les informations ont changé. Actualisez la proposition avant de valider.')
        info = d._archive.info(doc)
        category = d._archive.category(info.get('document_type', 'invoice'))
        path = safe_path(payload.get('path'), category)
        creditor = session.get(d.Creditor, doc.creditor_id) if doc.creditor_id else None
        catalogue = d._archive.catalogue()
        if not supplier or not creditor or not catalogue or d._archive.key(creditor.name) != d._archive.key(catalogue['company']):
            raise HTTPException(422, 'Confirmez le fournisseur et la société dans les informations du document.')
        if d._archive.monetary_kind(info.get('document_type', 'invoice')) and (doc.amount_minor is None or not doc.invoice_date or not doc.currency):
            raise HTTPException(422, 'La date, le montant et la devise restent à compléter.')
        source = session.get(d.DocumentSource, doc.id)
        evidence = d._duplicates.lookup(doc.sha256, source.source_sha256 if source else None)
        if evidence['matches']:
            raise HTTPException(409, {'code': 'archive_duplicate', 'message': 'Fichier identique déjà présent sur le serveur.', 'paths': evidence['matches']})
        root = d._filing_root(session)
        destination = d._safe_destination(root, path)
        # Resolve symlinks as well as traversal before any directory creation.
        if not destination.resolve().is_relative_to(root.resolve()):
            raise HTTPException(422, 'Le dossier doit rester dans l’archive NAS.')
        if not doc.proposed_filename or Path(doc.proposed_filename).name != doc.proposed_filename or '\\' in doc.proposed_filename:
            raise HTTPException(422, 'Le nom du fichier reste à confirmer.')
        doc.proposed_path = path
        confidence = dict(doc.confidence or {})
        confidence['manual_destination'] = {'score': 1., 'method': 'queue_confirmation', 'detail': path}
        doc.confidence = confidence
        try:
            # Explicit confirmation permits a new folder; keep hash verification,
            # simulation and conflict protection from the existing filing engine.
            if d._archive.monetary_kind(info.get('document_type', 'invoice')):
                final_path, digest, verified, replaced = d._previous_perform_filing(session, doc, 'ask')
            else:
                if source and source.converted:
                    from app.pipeline.act.naming import sanitize_component
                    final_path, digest, verified, replaced = d.file_document(d._original_path(doc, source), destination, sanitize_component(doc.original_filename), source.source_sha256, d._dry_run(session), 'ask')
                else:
                    final_path, digest, verified, replaced = d.file_document(d._inbox_path(doc), destination, doc.proposed_filename, doc.sha256, d._dry_run(session), 'ask')
            d._mark_filed(session, doc, final_path, digest, verified, replaced, False)
            session.commit()
        except FileExistsError:
            session.rollback()
            raise HTTPException(409, 'Ce nom existe déjà dans ce dossier. Aucun fichier remplacé.') from None
        except Exception as error:
            session.rollback()
            raise HTTPException(422, str(error)) from None
        return d._to_out(session, doc)

    app.include_router(router)
