"""CLI utility to start a Gmail push‑notification watch on INBOX."""

from .gmail_mail import _service   # same package

TOPIC = "projects/gmail-agent-466700/topics/gmail-agent-topic"


def main(user_id="demo"):
    svc = _service(user_id)
    watch = svc.users().watch(
        userId="me",
        body={
            "topicName": TOPIC,
            "labelIds": ["INBOX"],
            "labelFilterAction": "include",
        },
    ).execute()

    print("✅  Gmail watch started. Current historyId:", watch["historyId"])


if __name__ == "__main__":
    main()
