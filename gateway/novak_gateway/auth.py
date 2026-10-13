"""Who is calling. Three ways, strongest first.

1. A Pocket ID token (OIDC access token) whose audience is this gateway.
   The signature is checked against Pocket ID's published keys, so the caller
   cannot claim to be someone: the identity was issued.
2. A trusted client (Open WebUI) presenting its own key and naming the user in
   a header. Only as safe as the network: nothing but that client may reach
   the gateway. Which client may vouch is listed in gateway.yaml.
3. A key that belongs to one person (or the household), as a bearer token or in
   the URL path, for clients that can send neither (a Home Assistant pipeline,
   a script, a voice satellite).
"""
import json
import urllib.request
from dataclasses import dataclass

from .directory import Directory, key_matches


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class Identity:
    kind: str                # person | household
    name: str                # person name, or "household"
    via: str                 # oidc | client:<name> | key
    person: object = None


class OIDC:
    """Validates Pocket ID access tokens. Lazy: PyJWT is only needed if configured."""

    def __init__(self, issuer: str, audience: str, claim: str = "preferred_username"):
        self.issuer, self.audience, self.claim = issuer.rstrip("/"), audience, claim
        self._jwks = None

    def _client(self):
        if self._jwks is None:
            import jwt
            with urllib.request.urlopen(f"{self.issuer}/.well-known/openid-configuration", timeout=10) as r:
                uri = json.load(r)["jwks_uri"]
            self._jwks = jwt.PyJWKClient(uri)
        return self._jwks

    def username(self, token: str) -> str:
        import jwt
        try:
            key = self._client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256", "ES256", "EdDSA"],
                                audience=self.audience, issuer=self.issuer,
                                options={"require": ["exp", "iss", "aud"]})
        except jwt.PyJWTError as exc:
            raise AuthError(401, f"token rejected: {exc}")
        who = claims.get(self.claim) or claims.get("email") or claims.get("sub")
        if not who:
            raise AuthError(401, "token carries no username")
        return str(who)


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and len(token) > 40


def authenticate(d: Directory, headers, oidc: OIDC | None, path_key: str | None = None,
                 household_path: bool = False) -> Identity:
    auth = headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""

    if household_path:
        if key_matches(token or path_key or "", d.household_key_sha256):
            return Identity("household", "household", "key")
        raise AuthError(401, "household key required")

    if path_key:
        person = d.person_by_key(path_key)
        if person:
            return Identity("person", person.name, "key", person)
        raise AuthError(401, "unknown key")

    if not token:
        raise AuthError(401, "authentication required")

    if oidc and looks_like_jwt(token):
        who = oidc.username(token)
        person = d.find_person(who)
        if not person:
            raise AuthError(403, f"'{who}' is signed in but is not a person in Novak's directory")
        return Identity("person", person.name, "oidc", person)

    for client in d.settings.get("clients") or []:
        if key_matches(token, client.get("key_sha256")):
            header = client.get("user_header", "X-Novak-User")
            who = headers.get(header, "").strip()
            if not who:
                raise AuthError(400, f"client '{client['name']}' must name the user in {header}")
            person = d.find_person(who)
            if not person:
                raise AuthError(403, f"'{who}' is not a person in Novak's directory")
            return Identity("person", person.name, f"client:{client['name']}", person)

    person = d.person_by_key(token)
    if person:
        return Identity("person", person.name, "key", person)
    raise AuthError(401, "unrecognised credential")
