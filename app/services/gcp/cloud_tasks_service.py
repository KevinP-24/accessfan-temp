import os
import json
import logging
from datetime import datetime, timedelta, timezone

from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2

logger = logging.getLogger(__name__)


def enqueue_process_video_task(object_name: str, *, delay_seconds: int = 0) -> str:
    """
    Encola una Cloud Task para procesar UN video (por object_name).

    Env vars requeridas:
      - GCP_PROJECT_ID (o GOOGLE_CLOUD_PROJECT)
      - CLOUD_TASKS_LOCATION (default: us-east1)
      - CLOUD_TASKS_QUEUE (default: video-processing)
      - TASK_PROCESS_URL (URL completa a /tasks/process-video)
      - TASKS_OIDC_SA_EMAIL (service account email para firmar OIDC)
    """
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = (os.getenv("CLOUD_TASKS_LOCATION") or "us-east1").strip()
    queue = (os.getenv("CLOUD_TASKS_QUEUE") or "video-processing").strip()
    target_url = (os.getenv("TASK_PROCESS_URL") or "").strip()
    oidc_sa_email = (os.getenv("TASKS_OIDC_SA_EMAIL") or "").strip()

    if not project_id:
        raise RuntimeError("Falta env var: GCP_PROJECT_ID o GOOGLE_CLOUD_PROJECT")
    if not target_url:
        raise RuntimeError("Falta env var: TASK_PROCESS_URL")
    if not oidc_sa_email:
        raise RuntimeError("Falta env var: TASKS_OIDC_SA_EMAIL")

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project_id, location, queue)

    body = json.dumps({"object_name": object_name}).encode("utf-8")

    task: dict = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {"service_account_email": oidc_sa_email},
        }
    }

    if delay_seconds and delay_seconds > 0:
        dt = datetime.now(timezone.utc) + timedelta(seconds=int(delay_seconds))
        ts = timestamp_pb2.Timestamp()
        ts.FromDatetime(dt)
        task["schedule_time"] = ts

    resp = client.create_task(request={"parent": parent, "task": task})
    logger.info(f"[CLOUD_TASKS] enqueued task={resp.name} object={object_name}")
    return resp.name
