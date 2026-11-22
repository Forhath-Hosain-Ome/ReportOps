import logging
logger = logging.getLogger(__name__)


def shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, syns, _dir=None) -> str:
    for r, c, v in _labelp(syns):
        if dir is not None:
            ra = _dtbl(grid, (r, c))
            if ra:
                logger.info(f"'{v}' -> Cell Value [{ra}] Cell Address -> [{r}] [{c}]")
                return _tdtl(ra)
            
        else:
            ra = _dtbl(grid, (r,c), _dir) # Resolve Value
            if ra:
                nm = _tdtl(ra) # Normalize
                logger.info(f"'{v}' -> Cell Value [{nm}] Cell Address -> [{r}] [{c}]")
                return nm if nm else ""

    logger.warning(f"No value found for any matching label [{syns[0]}].")
    return ""