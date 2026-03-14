from celery.schedules import crontab
from data import init
from data.init_configs import get_config

init()

app = get_config().celery_app

app.autodiscover_tasks(["src.tasks"])

app.conf.beat_schedule = {
    "check-finished-events": {
        "task": "tasks.check_finished_events",
        "schedule": 300,
    },
    "morning-digest": {
        "task": "tasks.morning_digest",
        "schedule": crontab(hour=9, minute=0),
    },
}