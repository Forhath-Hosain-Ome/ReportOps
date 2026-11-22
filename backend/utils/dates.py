from django.utils.dateparse import parse_date

def _to_date(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    d = parse_date(s)
    if d:
        return d
    from datetime import datetime
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None