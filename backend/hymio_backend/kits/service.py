import httpx


class KitNotFound(Exception):
    pass


class KitNotInstalled(Exception):
    pass


class KitHostUnavailable(Exception):
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
