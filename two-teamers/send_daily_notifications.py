from app import create_app
from app.push_notifications import send_daily_game_notifications


if __name__ == "__main__":
    count = send_daily_game_notifications(create_app())
    print(f"Sent Daily Game notifications to {count} device(s).")
