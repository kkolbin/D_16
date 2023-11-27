from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from .tasks import send_weekly_email_notifications


def start():
    print("Scheduler started!")
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_weekly_email_notifications, 'cron', day_of_week='wed', hour=1, minute=27)
    scheduler.start()

