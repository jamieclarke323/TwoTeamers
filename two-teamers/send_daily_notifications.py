from app import create_app
from app.push_notifications import send_daily_notifications


if __name__ == "__main__":
    count = send_daily_notifications(create_app())
    print(f"Sent daily game notifications to {count} user(s).")
