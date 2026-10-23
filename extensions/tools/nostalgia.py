from core.protocol.datatype import ToolDefinition
from core.protocol.error import ToolExecutionError
from core.protocol.interface import Tool

from ._context_transport import call_context, request_context


class RememberTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "remember",
            "Save something about the user that should remain available in future conversations. "
            "Call this before replying when the user explicitly asks Hymio to remember something "
            "or clearly states a durable preference, fact, goal, relationship or routine about "
            "themselves. Pass the user's statement verbatim, not a reinterpretation.",
            {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The exact user statement to preserve",
                        "minLength": 1,
                        "maxLength": 16000,
                    },
                    "topic": {
                        "type": "string",
                        "description": "Short topic, such as food, work or weekly routine",
                        "maxLength": 80,
                    },
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        text = invocation.arguments.get("text")
        topic = invocation.arguments.get("topic")
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ToolExecutionError("Provide the user's statement in text")
        if topic is not None and (not isinstance(topic, str) or len(topic) > 80):
            raise ToolExecutionError("Topic must be a short string")
        context = {"text": text, "role": "user", "recorded_by": "agent"}
        if topic:
            context["topic"] = topic
        return request_context(
            invocation,
            {
                "action": "records.append",
                "operation_id": "remember:" + invocation.invocation_id,
                "data": {
                    "item_type": "context",
                    "context_type": "conversation",
                    "context": context,
                    "source": {
                        "kind": "conversation",
                        "namespace": "hymio.agent",
                        "external_id": "remember:" + invocation.invocation_id,
                        "version": "1",
                        "parser": "hymio.remember.v1",
                    },
                },
            },
        )


class RecallTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "recall",
            "Search what Hymio already knows about the user before answering questions about "
            "their preferences, history, relationships, goals or routines. Use this instead of "
            "guessing from the current chat transcript.",
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to look for in the user's saved context",
                        "minLength": 1,
                        "maxLength": 500,
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        query = invocation.arguments.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise ToolExecutionError("Provide a query to recall")
        return request_context(
            invocation,
            {
                "action": "search",
                "data": {
                    "target": "all",
                    "mode": "text",
                    "query": query,
                    "filters": {},
                    "limit": 10,
                },
            },
        )


class NostalgiaTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "nostalgia",
            "Advanced personal-context operations: inspect provenance, update records and "
            "maintain a Hymio-created dreaming draft. For ordinary remembering or recall, use "
            "the remember or recall tools. "
            "Responses contain data and etag. Writes require a stable operation_id; "
            "reuse it only for an exact retry. Load the dreaming skill for draft edits.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "assembly",
                        "events",
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
