import logging
logger = logging.getLogger(__name__)

def process_extraction(grid ,path ,record ,_func ,name ,report_type=None):
    try:
        if report_type is not None:
            data = _func(grid, path, report_type)
        else:
            data = _func(grid, path)
        
        if not data:
            logger.info(f"{name} -> Not found on primary sheet")
            return None
        for k, v in data.items():
            if v and str(v).strip():
                setattr(record, k, v)
                logger.info(f"  [{k}] -> '{v}'")
        return data
    except Exception as exc:
        logger.error(f"[{path.name}] Extraction FAILED: {exc}")
        return None