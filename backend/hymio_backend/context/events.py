"""At-least-once callback delivery. One worker per user/consumer; deduplicate event IDs."""

import sqlite3
from contextlib import closing


def deliver(client, user_id, consumer, database, callback, *, limit=50):
    """Callback returns only after durable downstream acceptance; failures remain replayable."""
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS context_consumers "
            "(user_id TEXT, consumer TEXT, after_id TEXT, PRIMARY KEY(user_id,consumer))"
        )
        row = conn.execute(
            "SELECT after_id FROM context_consumers WHERE user_id=? AND consumer=?",
            (user_id, consumer),
        ).fetchone()
        after = row[0] if row else "0"
    page = client.call(user_id, "events", query={"after": after, "limit": limit})["data"]
    for event in page["items"]:
        event_id = event["id"]
        callback(event)
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute(
                "INSERT INTO context_consumers VALUES (?,?,?) "
                "ON CONFLICT(user_id,consumer) DO UPDATE SET after_id=excluded.after_id",
                (user_id, consumer, event_id),
            )
        after = event_id
    return {"after": after, "has_more": page["has_more"]}
