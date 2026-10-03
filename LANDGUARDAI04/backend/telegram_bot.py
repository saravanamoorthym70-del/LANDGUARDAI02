import logging
import os
import time
from typing import Any, Callable

import requests

from backend import record_store
from backend.telegram_alerts import _environment_flag, _parse_subscription_request
from backend.telegram_alerts import send_telegram_message


logger = logging.getLogger(__name__)


def handle_update(
    update: dict[str, Any],
    send_message: Callable[[str, str], None],
    test_mode: bool | None = None,
    test_chat_id: str | None = None,
) -> None:
    if test_mode is None:
        test_mode = _environment_flag("TELEGRAM_TEST_MODE", True)
    if test_chat_id is None:
        test_chat_id = os.getenv("TELEGRAM_TEST_CHAT_ID")

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    text = str(message.get("text", "")).strip()
    if not chat_id or not text.startswith("/"):
        return

    command, _, arguments = text.partition(" ")
    command = command.split("@", maxsplit=1)[0].lower()
    if test_mode and not test_chat_id:
        if command in {"/start", "/whoami"}:
            send_message(
                chat_id,
                f"Test mode is enabled. Your chat ID is {chat_id}. "
                "Set TELEGRAM_TEST_CHAT_ID to this value, then restart the bot.",
            )
        return
    if test_mode and chat_id != str(test_chat_id):
        logger.info("Ignored Telegram command outside the configured test chat")
        return

    if command in {"/start", "/help"}:
        send_message(
            chat_id,
            "LANDGUARD AI prototype screening alerts.\n"
            "/subscribe location <lat> <lon> [name]\n"
            "/subscribe district <district> in <state>\n"
            "/subscriptions\n"
            "/unsubscribe <subscription_id>\n"
            "Scores are not official warnings.",
        )
    elif command == "/subscribe":
        try:
            subscription = record_store.create_alert_subscription(
                _parse_subscription_request(chat_id, arguments)
            )
        except (ValueError, KeyError) as exc:
            send_message(chat_id, str(exc))
            return
        send_message(
            chat_id,
            f"Subscribed to {subscription['label']} (ID {subscription['subscription_id']}). "
            "Prototype screening score only, not an official warning.",
        )
    elif command == "/subscriptions":
        subscriptions = record_store.list_alert_subscriptions(chat_id)
        if not subscriptions:
            send_message(chat_id, "No active subscriptions.")
            return
        lines = [
            f"{item['subscription_id']}: {item['label']}"
            for item in subscriptions
        ]
        send_message(chat_id, "Your alert subscriptions:\n" + "\n".join(lines))
    elif command == "/unsubscribe":
        subscription_id = arguments.strip()
        if not subscription_id:
            send_message(
                chat_id,
                "Provide an ID from /subscriptions: /unsubscribe <subscription_id>",
            )
        elif record_store.delete_alert_subscription(subscription_id, chat_id):
            send_message(chat_id, "Subscription removed.")
        else:
            send_message(chat_id, "No matching subscription was found for this chat.")
    else:
        send_message(chat_id, "Unknown command. Send /help for available commands.")


def poll_bot(
    token: str,
    test_mode: bool | None = None,
    test_chat_id: str | None = None,
    get: Callable[..., Any] | None = None,
    send_message: Callable[[str, str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_polls: int | None = None,
) -> None:
    if test_mode is None:
        test_mode = _environment_flag("TELEGRAM_TEST_MODE", True)
    if test_chat_id is None:
        test_chat_id = os.getenv("TELEGRAM_TEST_CHAT_ID")
    get = get or requests.get
    if send_message is None:
        send_message = lambda chat_id, text: send_telegram_message(
            chat_id,
            text,
            token=token,
            test_mode=test_mode,
            test_chat_id=test_chat_id,
        )

    offset = 0
    polls = 0
    while max_polls is None or polls < max_polls:
        try:
            response = get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 25, "offset": offset},
                timeout=35,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError("Telegram rejected the polling request")
            for update in payload.get("result", []):
                offset = max(offset, int(update["update_id"]) + 1)
                handle_update(update, send_message, test_mode, test_chat_id)
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            logger.warning("Telegram polling failed: %s", type(exc).__name__)
            sleep(5)
        polls += 1


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in the project-root .env before starting the bot.")
    record_store.init_db()
    poll_bot(token)


if __name__ == "__main__":
    main()