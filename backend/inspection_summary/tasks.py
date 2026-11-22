from celery import shared_task

from .services import TASK_HARD_LIMIT, cleanup_expired_jobs, generate_job, recover_dispatches, recover_processing_jobs


@shared_task(bind=True, name="inspection_summary.generate", queue="celery", max_retries=0,
             ignore_result=True, soft_time_limit=1200, time_limit=TASK_HARD_LIMIT)
def generate_inspection_summary(self, job_id, generation, token):
    return generate_job(job_id, generation, token)


@shared_task(name="inspection_summary.cleanup_expired", queue="celery", ignore_result=True, max_retries=0)
def cleanup_expired():
    recover_processing_jobs()
    recover_dispatches()
    return cleanup_expired_jobs()
