import argparse
import sys

from app import create_app
from app.push_notifications import send_test_notification


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a test push only to one account's subscribed devices."
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Email address of the account whose devices should receive the test.",
    )
    parser.add_argument(
        "--confirm-send",
        action="store_true",
        help="Required to send a real test notification.",
    )
    args = parser.parse_args()
    if not args.confirm_send:
        parser.error("Pass --confirm-send to send a test notification.")

    try:
        sent, failed = send_test_notification(create_app(), args.email)
    except (RuntimeError, ValueError) as error:
        print(f"Test push could not be sent: {error}", file=sys.stderr)
        return 1
    print(f"Push service accepted {sent} notification(s); {failed} device(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
