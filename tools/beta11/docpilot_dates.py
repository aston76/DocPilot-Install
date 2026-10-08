"""Invoice dates with labelled evidence, excluding payment and shipment dates."""
import re
import unicodedata
from datetime import date

ISSUE = r'invoice\s+date|date\s+issued|date\s+of\s+issue|issued\s+on|issue\s+date|date\s+(?:de\s+(?:la\s+)?)?facture|date\s+d[\x27’]?emission|rechnungsdatum|data\s+(?:della\s+)?fattura|fecha\s+(?:de\s+)?factura|data\s+de\s+emissao'
OTHER = r'due\s+date|payment\s+date|arrival\s+date|departure\s+date|delivery\s+date|order\s+date|date\s+d[\x27’]?(?:arrivee|echeance|expedition)|date\s+de\s+(?:livraison|commande|paiement)|echeance|arrival|departure|livraison|delivery|dispatch|shipping|payable|faellig\w*|zahlbar|scadenza|vencimiento|liefer\w*|auftrag\w*|commande|bestell\w*'
LABELS = re.compile('(?P<issue>'+ISSUE+')|(?P<other>'+OTHER+r')|(?P<generic>\b(?:date|datum|data|fecha)\b)', re.I)
NUMERIC = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b')

def candidates(text):
    plain = ''.join(c for c in unicodedata.normalize('NFKD', text or '') if not unicodedata.combining(c)).lower()
    found = []
    for match in NUMERIC.finditer(plain):
        try:
            value = date(int(match[1]),int(match[2]),int(match[3])) if match[1] else date(int(match[6]),int(match[5]),int(match[4]))
        except ValueError:
            continue
        start = plain.rfind('\n',0,match.start())+1
        context = plain[start:match.start()]
        if not context.strip():
            lines = plain[:start].rstrip().splitlines()
            context = lines[-1] if lines else ''
        labels = list(LABELS.finditer(context))
        label = labels[-1] if labels else None
        kind = label.lastgroup if label else 'unlabelled'
        found.append({'date':value.isoformat(),'kind':kind,'label':label.group() if label else '', 'evidence':(context.strip()+' '+match.group()).strip()[-200:]})
    return found

def invoice_dates(text):
    entries = candidates(text)
    explicit = {e['date'] for e in entries if e['kind']=='issue'}
    if explicit:
        return explicit
    return {e['date'] for e in entries if e['kind']=='generic'}
