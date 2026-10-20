from core.protocol.datatype import ToolDefinition
from core.protocol.interface import Tool

from ._context_transport import call_context


class NostalgiaTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "nostalgia",
            "Read personal context and maintain a Hymio-created dreaming draft. "
            "Use injection/search before answering questions about earlier information. "
            "Responses contain data and etag. Writes require a stable operation_id; "
            "reuse it only for an exact retry. Load the dreaming skill for draft edits.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "injection",
                            "search",
                            "records.list",
                            "records.read",
                            "records.append",
                            "records.mark",
                            "artifacts.read",
                            "artifacts.put",
                            "artifacts.delete",
                            "dreams.read",
                            "dreams.commit",
                            "dreams.abort",
                        ],
                    },
                    "item_id": {"type": "string", "description": "Original row or artifact ID"},
                    "dream_id": {"type": "string"},
                    "data": {"type": "object", "description": "API JSON body"},
                    "query": {"type": "object", "description": "API filters/page cursor"},
                    "etag": {"type": "string", "description": "Exact ETag from a preceding read"},
                    "create": {"type": "boolean", "description": "If-None-Match: * for new cards"},
                    "operation_id": {"type": "string", "minLength": 1, "maxLength": 160},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        return call_context(invocation)
