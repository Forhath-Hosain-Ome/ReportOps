COUNTRY_MAP = {
    "01": "JAPAN",
    "05": "USA",
    "07": "GERMANY",
    "10": "BANGLADESH",
}


def get_country(value) -> str:
    if value is None:
        return ""

    value = str(value).strip()

    if len(value) < 2:
        return ""

    return COUNTRY_MAP.get(value[:2], "")