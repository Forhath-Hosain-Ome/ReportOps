import logging
logger = logging.getLogger(__name__)

def base_extract(grid, path, _labelp, _inlineval, _rslv,syns ,dir ,frm: str = ""):
    positions = _labelp(syns)

    for r, c, v in positions:
        for syn in syns:
            value = _inlineval(syn, v)
            if value:
                logger.info(f"'{v}' -> Cell Value [{value}] Cell Address -> [{r}] [{c}]")
                return value
        value = _rslv(grid, (r, c), dir)
        if value:
            logger.info(f"'{v}' -> Cell Value [{value}] Cell Address -> [{r}] [{c}]")
            return value
    logger.warning(f"No value found for any matching label [{syns[0]}].")
    return ""