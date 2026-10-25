import json

from . import devsource


class GeneratedSourceKit:
    """React application with a bounded generated Python operation backend."""

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
        descriptor = next(
            (
                item
                for item in self.manifest["operations"]
                if item["id"] == operation
            ),
            None,
        )
        if descriptor is None:
            raise ValueError("Unknown application operation")
        project = self.store.project(user_id, self.kit_id)
        app = json.loads(project["files"]["app.json"])
        source_operation = next(
            (item for item in app["operations"] if item["id"] == operation),
            None,
        )
        if source_operation is None:
            raise ValueError("Unknown application operation")
        result, mutations = devsource.invoke_python(
            project["files"],
            source_operation["handler"],
            arguments,
            self.store.all_app_records(user_id, self.kit_id),
        )
        if descriptor["effect"] == "read":
            if mutations:
                raise ValueError("Read operations cannot modify application data")
            return result
        return self.store.apply_app_mutations(
            user_id,
            self.kit_id,
            idempotency_key,
            operation,
            mutations,
            result,
        )
