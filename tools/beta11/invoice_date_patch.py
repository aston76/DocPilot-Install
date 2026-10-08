_MONTH_NAMES = (
    'janvier january januar gennaio enero janeiro',
    'fevrier february februar febbraio febrero fevereiro',
    'mars march marz maerz marzo marco',
    'avril april aprile abril',
    'mai may maggio mayo maio',
    'juin june juni giugno junio junho',
    'juillet july juli luglio julio julho',
    'aout august agosto',
    'septembre september settembre septiembre setembro',
    'octobre october oktober ottobre octubre outubro',
    'novembre november novembre noviembre novembro',
    'decembre december dezember dicembre diciembre dezembro',
)

def find_invoice_date(text):
    months = {name: number for number, names in enumerate(_MONTH_NAMES, 1) for name in names.split()}
    normalized = _plain(text).lower()
    pattern = re.compile(r'\b(\d{1,2})\.?\s+(?:de\s+)?(' + '|'.join(months) + r')\s+(?:de\s+)?(\d{4})\b|\b(' + '|'.join(months) + r')\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})\b')
    candidates = []
    matches = []
    for match in pattern.finditer(normalized):
        day, month, year = (match[1], match[2], match[3]) if match[1] else (match[5], match[4], match[6])
        try: value = date(int(year), months[month], int(day))
        except ValueError: continue
        matches.append((match.start(), match.end(), value))
    for match in re.finditer(r'\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b', normalized):
        try:
            value = date(int(match[1]), int(match[2]), int(match[3])) if match[1] else date(int(match[6]), int(match[5]), int(match[4]))
        except ValueError: continue
        matches.append((match.start(), match.end(), value))
    invoice_label = r'invoice\s+date|date\s+issued|issue\s+date|date\s+d[\x27’]?emission|date\s+(?:de\s+(?:la\s+)?)?facture|rechnungsdatum|data\s+(?:della\s+)?fattura|fecha\s+(?:de\s+)?factura|data\s+de\s+emissao|date\s+of\s+issue|issued\s+on'
    other_label = r'echeance|payable|expedition|dispatch|shipping|arrival\s+date|departure\s+date|due\s+date|payment\s+date|faellig\w*|zahlbar|scadenza|vencimiento|delivery|livraison|liefer\w*|auftrag\w*|commande|order\s+date|service|circulation|reparation|bestell\w*'
    labels = re.compile('(?P<invoice>' + invoice_label + ')|(?P<other>' + other_label + r')|(?P<generic>\b(?:date|datum|data|fecha)\b)')
    for start, end, value in sorted(matches):
        line_start = normalized.rfind('\n', 0, start) + 1
        context = normalized[line_start:start]
        if not context.strip():
            previous = normalized[:line_start].rstrip('\n').splitlines()
            if previous: context = previous[-1]
        preceding = list(labels.finditer(context))
        if preceding:
            label = preceding[-1]
            if label.lastgroup == 'other': continue
            score = 4 if label.lastgroup == 'invoice' else 3
        else:
            score = 1 if start < 1800 else 0
        if score: candidates.append((score, value))
    if candidates:
        best = max(score for score, _ in candidates)
        values = {value for score, value in candidates if score == best}
        if len(values) == 1: return next(iter(values)), True
        return None, False
    return None, False

_company_name_original_party_key = _party_key
def _party_key(value):
    key = _company_name_original_party_key(value)
    return 'viniwine' if key == 'viniwinesarl' else key
_FIXED_CREDITORS = {'viniwine': 'ViniWine Sàrl', 'wineoclock': "Wine O'Clock"}
