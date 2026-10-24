from .store import CATEGORIES


class LedgerKit:
    def __init__(self, store):
        self.store = store

    def invoke(self, user_id, operation, arguments, idempotency_key):
        if operation == "entries.create":
            result = self.store.create_entry(user_id, arguments, idempotency_key)
            result["summary"] = self.store.summary(user_id)
            return result
        if operation == "entries.list":
            return {
                "items": self.store.list_entries(user_id, arguments.get("limit", 20)),
                "summary": self.store.summary(user_id),
            }
        if operation == "summary":
            return self.store.summary(user_id)
        raise ValueError("Unknown ledger operation")

    def preview(self, user_id):
        summary = self.store.summary(user_id)
        entries = self.store.list_entries(user_id, 1)
        return {
            "label": "本月支出",
            "value": f"¥{summary['total']:.2f}",
            "detail": f"{summary['count']} 笔记录",
            "latest": (
                entries[0]["note"] or CATEGORIES[entries[0]["category"]] if entries else ""
            ),
        }
