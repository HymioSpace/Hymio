class GeneratedCollectionKit:
    """Backend operations for a generated application with custom web UI."""

    def __init__(self, store, manifest):
        self.store = store
        self.manifest = manifest
        self.kit_id = manifest["id"]

    def preview(self, user_id):
        count = self.store.count_records(user_id, self.kit_id)
        return {
            "label": "已记录",
            "value": f"{count} 条",
            "detail": self.manifest["display"]["tagline"],
            "latest": "",
        }

    def invoke(self, user_id, operation, arguments, idempotency_key):
        if operation == "items.create":
            result = self.store.create_record(
                user_id, self.kit_id, arguments, idempotency_key
            )
            result["count"] = self.store.count_records(user_id, self.kit_id)
            return result
        if operation == "items.list":
            return {
                "items": self.store.list_records(
                    user_id, self.kit_id, arguments.get("limit", 20)
                ),
                "count": self.store.count_records(user_id, self.kit_id),
            }
        if operation == "summary":
            return {
                "count": self.store.count_records(user_id, self.kit_id),
                "title": self.manifest["display"]["name"],
            }
        raise ValueError("Unknown generated Kit operation")
