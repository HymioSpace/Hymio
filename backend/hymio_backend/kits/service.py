import hashlib
import logging

import httpx

from ..tasks.credentials import issue

_log = logging.getLogger(__name__)


class KitNotFound(Exception):
    pass


class KitNotInstalled(Exception):
    pass


class KitHostUnavailable(Exception):
    pass


class KitRequestError(Exception):
    pass


class KitsService:
    """Authenticated Backend proxy for the independent Kit Host service."""

    def __init__(self, settings, client):
        self.settings = settings
        self.client = client

    async def _post(self, path, data):
        token = self.settings.service_token_file.read_text().strip()
        try:
            response = await self.client.post(
                self.settings.kits_url.rstrip("/") + path,
                json=data,
                headers={"Authorization": "Bearer " + token},
            )
        except httpx.HTTPError as exc:
            raise KitHostUnavailable() from exc
        if response.status_code == 404:
            raise KitNotFound()
        if response.status_code == 409:
            raise KitNotInstalled()
        if response.status_code == 400:
            try:
                message = response.json().get("message")
            except ValueError:
                message = ""
            raise KitRequestError(
                message if isinstance(message, str) and message else "Invalid application request"
            )
        if not response.is_success:
            raise KitHostUnavailable()
        try:
            value = response.json()
        except ValueError as exc:
            raise KitHostUnavailable() from exc
        if not isinstance(value, dict):
            raise KitHostUnavailable()
        return value

    async def _oath(self, user_id, path, data):
        oath_biz = getattr(self.settings, "oath_biz", "")
        if not oath_biz:
            raise KitHostUnavailable()
        try:
            response = await self.client.post(
                oath_biz.rstrip("/") + path,
                json=data,
                headers={"Authorization": "Bearer " + issue(self.settings, user_id)},
            )
        except httpx.HTTPError as exc:
            raise KitHostUnavailable() from exc
        if not response.is_success:
            raise KitHostUnavailable()
        try:
            value = response.json()
        except ValueError as exc:
            raise KitHostUnavailable() from exc
        if not isinstance(value, dict):
            raise KitHostUnavailable()
        return value

    async def catalog(self, user_id):
        return (await self._post("/v1/catalog", {"user_id": user_id}))["kits"]

    async def install(self, user_id, kit_id):
        return await self._post("/v1/install", {"user_id": user_id, "kit_id": kit_id})

    async def uninstall(self, user_id, kit_id):
        return await self._post("/v1/uninstall", {"user_id": user_id, "kit_id": kit_id})

    async def app(self, user_id, kit_id):
        return await self._post("/v1/app", {"user_id": user_id, "kit_id": kit_id})

    async def generate(self, user_id, spec):
        return await self._post("/v1/generate", {"user_id": user_id, "spec": spec})

    async def start_coding(self, user_id, spec, request_id):
        project = await self.create_project(user_id, spec, request_id)
        agent_id = await self._start_agent(
            user_id,
            project,
            spec.get("requirements", ""),
            request_id,
            notify_parent=True,
        )
        return {
            "kit_id": project["kit_id"],
            "agent_id": agent_id,
            "status": "coding",
            "display": project["display"],
        }

    async def _start_agent(
        self,
        user_id,
        project,
        requirements,
        request_id,
        notify_parent,
    ):
        display = project["display"]
        objective = (
            f"Build the application “{display['name']}” from the React/Python project "
            f"already assigned to this coding context. Product request: {requirements}. "
            "Keep the generated API contract stable unless the request requires a new data "
            "model. Use kit_dev to inspect files, make focused patches, check, and publish."
        )
        success = (
            "React builds with no errors; Python API validation passes; the page has a "
            "finished empty/loading/error state; publish succeeds; the result is useful on "
            "a 390 px iPhone without horizontal overflow."
        )
        spawned = await self._oath(
            user_id,
            "/subagents/spawn",
            {
                "request_id": "kit-coding:" + project["kit_id"],
                "title": "应用开发：" + display["name"],
                "objective": objective,
                "success_criteria": success,
                "notify_parent": notify_parent,
                "defer_start": True,
                "max_steps": 100,
                "timeout_seconds": 3600,
            },
        )
        agent_id = spawned.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise KitHostUnavailable()
        await self.bind_project_agent(user_id, project["kit_id"], agent_id)
        await self._oath(
            user_id,
            "/subagents/continue",
            {
                "agent_id": agent_id,
                "message_id": "kit-start:" + str(request_id or project["kit_id"]),
                "content": objective,
                "success_criteria": success,
                "notify_parent": notify_parent,
                "max_steps": 100,
                "timeout_seconds": 3600,
            },
        )
        await self.add_editor_message(
            user_id,
            project["kit_id"],
            "main:" + str(request_id or project["kit_id"]),
            "main_agent",
            str(requirements),
        )
        return agent_id

    async def continue_coding(
        self,
        user_id,
        kit_id,
        content,
        message_id,
        notify_parent=False,
        author="user",
    ):
        editor = await self.editor(user_id, kit_id)
        agent_id = editor.get("coding_agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise KitHostUnavailable()
        await self.add_editor_message(
            user_id, kit_id, message_id, author, content
        )
        await self._oath(
            user_id,
            "/subagents/continue",
            {
                "agent_id": agent_id,
                "message_id": message_id,
                "content": content,
                "success_criteria": (
                    "Deliver the requested application change, keep existing records, "
                    "make check pass, and publish only when the result is complete."
                ),
                "notify_parent": notify_parent,
                "max_steps": 100,
                "timeout_seconds": 3600,
            },
        )
        return {"accepted": True, "kit_id": kit_id}

    async def editor_status(self, user_id, kit_id):
        editor = await self.editor(user_id, kit_id)
        agent_id = editor.get("coding_agent_id")
        if isinstance(agent_id, str) and agent_id:
            try:
                agent = await self._oath(
                    user_id,
                    "/subagents/get",
                    {"agent_id": agent_id},
                )
                editor["agent_status"] = agent.get("status", "unknown")
                editor["agent_result"] = agent.get("result", "")
            except KitHostUnavailable:
                editor["agent_status"] = "unavailable"
                editor["agent_result"] = ""
        else:
            editor["agent_status"] = "not_started"
            editor["agent_result"] = ""
        return editor

    async def create_project(self, user_id, spec, request_id=None):
        return await self._post(
            "/v1/project/create",
            {"user_id": user_id, "spec": spec, "request_id": request_id},
        )

    async def bind_project_agent(self, user_id, kit_id, agent_id):
        return await self._post(
            "/v1/project/bind-agent",
            {"user_id": user_id, "kit_id": kit_id, "agent_id": agent_id},
        )

    async def dev_context(self, user_id, agent_id):
        return await self._post(
            "/v1/dev/context", {"user_id": user_id, "agent_id": agent_id}
        )

    async def dev_invoke(
        self,
        user_id,
        agent_id,
        dev_action,
        arguments,
        idempotency_key,
    ):
        return await self._post(
            "/v1/dev",
            {
                "user_id": user_id,
                "agent_id": agent_id,
                "dev_action": dev_action,
                "arguments": arguments,
                "idempotency_key": idempotency_key,
            },
        )

    async def editor(self, user_id, kit_id):
        return await self._post(
            "/v1/editor", {"user_id": user_id, "kit_id": kit_id}
        )

    async def add_editor_message(
        self, user_id, kit_id, message_id, author, content
    ):
        return await self._post(
            "/v1/editor/message",
            {
                "user_id": user_id,
                "kit_id": kit_id,
                "message_id": message_id,
                "author": author,
                "content": content,
            },
        )

    async def delete_generated(self, user_id, kit_id, idempotency_key):
        try:
            editor = await self.editor(user_id, kit_id)
            agent_id = editor.get("coding_agent_id")
        except KitHostUnavailable:
            agent_id = None
        result = await self._post(
            "/v1/delete-generated",
            {
                "user_id": user_id,
                "kit_id": kit_id,
                "idempotency_key": idempotency_key,
            },
        )
        if isinstance(agent_id, str) and agent_id:
            try:
                await self._oath(
                    user_id,
                    "/subagents/cancel",
                    {"agent_id": agent_id},
                )
            except KitHostUnavailable:
                pass
        return result

    async def agent_context(self, user_id):
        return await self._post("/v1/agent-context", {"user_id": user_id})

    async def invoke(
        self,
        user_id,
        kit_id,
        operation,
        arguments,
        idempotency_key,
    ):
        return await self._post(
            "/v1/invoke",
            {
                "user_id": user_id,
                "kit_id": kit_id,
                "operation": operation,
                "arguments": arguments,
                "idempotency_key": idempotency_key,
            },
        )

    async def record_user_interaction(
        self, user_id, invocation, idempotency_key
    ):
        if invocation.get("effect") != "write":
            return
        oath_biz = getattr(self.settings, "oath_biz", "")
        if not oath_biz:
            return
        application = invocation.get("application")
        result = invocation.get("result")
        summary = {}
        if isinstance(result, dict):
            message = result.get("message")
            if isinstance(message, str) and message:
                summary["message"] = message[:500]
            count = result.get("count")
            if type(count) is int:
                summary["count"] = count
            entry = result.get("entry") or result.get("item")
            if isinstance(entry, dict):
                for key in ("id", "revision"):
                    value = entry.get(key)
                    if isinstance(value, (str, int)) and not isinstance(value, bool):
                        summary[key] = value
        event_id = hashlib.sha256(
            (user_id + "\0" + idempotency_key).encode()
        ).hexdigest()
        try:
            response = await self.client.post(
                oath_biz.rstrip("/") + "/events",
                headers={
                    "Authorization": "Bearer " + issue(self.settings, user_id),
                    "X-Oath-User-Id": user_id,
                },
                json={
                    "type": "app.kit.interaction",
                    "queue": "user",
                    "defer_wake": True,
                    "event_id": "kit-interaction-" + event_id,
                    "payload": {
                        "kit_id": invocation.get("kit_id"),
                        "kit_name": (
                            application.get("name")
                            if isinstance(application, dict)
                            else invocation.get("kit_id")
                        ),
                        "operation": invocation.get("operation"),
                        "result": summary,
                    },
                },
            )
            response.raise_for_status()
        except Exception:
            _log.warning(
                "Kit interaction event could not be queued",
                exc_info=True,
            )
