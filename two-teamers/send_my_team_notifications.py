from app import create_app
from app.push_notifications import send_my_team_notifications


if __name__ == "__main__":
    count = send_my_team_notifications(create_app())
    print(f"Sent My Team notifications to {count} device(s).")
