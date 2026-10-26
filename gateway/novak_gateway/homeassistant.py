"""A small Home Assistant REST client for the built-in house tools (decision #77).

Two endpoints only: render a template (the floor, area and light lookup) and call a light service. The
credential is a long-lived token for a dedicated admin user (`HA_<id>_ADMIN_API_TOKEN`), not a person's
own account; HA lets only an admin render templates. The gateway never exposes this client to a model:
it can do just the two things the house tools do, however the token is scoped.
"""
import json
import urllib.error
import urllib.request


class HAError(RuntimeError):
    pass


class HAClient:
    def __init__(self, url: str, token: str, timeout: float = 20):
        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout

    def _post(self, path: str, body: dict) -> str:
        req = urllib.request.Request(f"{self.url}{path}", data=json.dumps(body).encode(), headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:160].strip()
            hint = " (the token must belong to an admin user to render templates)" if exc.code in (401, 403) else ""
            raise HAError(f"Home Assistant answered {exc.code}{hint}: {detail}") from None

    def template(self, template: str) -> str:
        return self._post("/api/template", {"template": template})

    def call_service(self, domain: str, service: str, entity_id: str, data: dict | None = None) -> None:
        self._post(f"/api/services/{domain}/{service}", {"entity_id": entity_id, **(data or {})})
