import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from novak_gateway.auth import OIDC
from test_gateway import World


def issuer():
    """A stand-in Pocket ID: discovery document and published keys."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            base = f"http://127.0.0.1:{srv.server_port}"
            doc = ({"issuer": base, "jwks_uri": base + "/jwks"} if "openid-configuration" in self.path
                   else {"keys": [jwk]})
            body = json.dumps(doc).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, key


class OIDCTests(unittest.TestCase):
    def setUp(self):
        self.srv, self.key = issuer()
        self.addCleanup(self.srv.shutdown)
        self.iss = f"http://127.0.0.1:{self.srv.server_port}"
        self.aud = "http://gw.test/mcp"
        self.w = World(self, oidc=OIDC(self.iss, self.aud))

    def token(self, **over):
        claims = {"iss": self.iss, "aud": self.aud, "exp": int(time.time()) + 300,
                  "sub": "u1", "preferred_username": "tmeuze", **over}
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "k1"})

    def test_a_valid_pocket_id_token_is_the_person(self):
        code, t = self.w.tools(token=self.token())
        self.assertEqual(code, 200)
        self.assertTrue(all(n.startswith("hs_tmeuze__") for n in t))
        self.assertEqual(self.w.audit.recent()[0]["via"] if self.w.audit.recent() else "oidc", "oidc")

    def test_username_picks_the_person(self):
        _, t = self.w.tools(token=self.token(preferred_username="ushy"))
        self.assertTrue(all(n.startswith("hs_ushy__") for n in t))

    def test_wrong_audience_expired_and_forged_tokens_are_refused(self):
        self.assertEqual(self.w.tools(token=self.token(aud="http://elsewhere/mcp"))[0], 401)
        self.assertEqual(self.w.tools(token=self.token(exp=int(time.time()) - 10))[0], 401)
        forged = jwt.encode({"iss": self.iss, "aud": self.aud, "exp": int(time.time()) + 300,
                             "preferred_username": "tmeuze"},
                            rsa.generate_private_key(public_exponent=65537, key_size=2048),
                            algorithm="RS256", headers={"kid": "k1"})
        self.assertEqual(self.w.tools(token=forged)[0], 401)

    def test_signed_in_but_unknown_person_is_forbidden(self):
        self.assertEqual(self.w.tools(token=self.token(preferred_username="stranger"))[0], 403)

    def test_discovery_document_and_challenge_point_at_pocket_id(self):
        import urllib.request, urllib.error
        meta = json.load(urllib.request.urlopen(f"{self.w.base}/.well-known/oauth-protected-resource"))
        self.assertEqual(meta["authorization_servers"], [self.iss])
        self.assertEqual(meta["resource"], "http://gw.test/mcp")
        try:
            urllib.request.urlopen(urllib.request.Request(f"{self.w.base}/mcp", data=b"{}", method="POST"))
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)
            self.assertIn("resource_metadata=", e.headers["WWW-Authenticate"])


if __name__ == "__main__":
    unittest.main()
