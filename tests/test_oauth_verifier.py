import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from memorycore.http_auth import JWKSClientVerifier, OAuthClientPolicy, TokenConfigurationError
from memorycore.mcp_server import create_server
from memorycore.memory_service import MemoryService


@pytest.fixture
def verifier():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = JWKSClientVerifier(
        issuer="https://login.example.test/", audience="https://memory.example.test/mcp",
        jwks_url="https://login.example.test/jwks",
        identities=[OAuthClientPolicy(client_id="hermes-client", client_role="writer",
                                      allowed_projects=frozenset({"alpha"}))],
    )
    verifier._keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
    return verifier, key


def signed(key, **changes):
    claims = {"iss": "https://login.example.test/", "aud": "https://memory.example.test/mcp",
              "sub": "hermes-client", "iat": int(time.time()), "exp": int(time.time()) + 300,
              "scope": "memorycore"}
    claims.update(changes)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.mark.asyncio
async def test_verified_subject_maps_to_local_role(verifier):
    provider, key = verifier
    result = await provider.verify_token(signed(key))
    assert result.client_id == "hermes-client"
    assert provider.identity_for_client(result.client_id).client_role == "writer"
    assert provider.identity_for_client(result.client_id).allowed_projects == frozenset({"alpha"})


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"aud": "https://other.example.test/mcp"}, {"iss": "https://other.example.test/"},
    {"exp": 1}, {"sub": "unregistered-client"}, {"scope": "other"},
])
async def test_invalid_or_unauthorized_claims_fail_closed(verifier, changes):
    provider, key = verifier
    assert await provider.verify_token(signed(key, **changes)) is None


@pytest.mark.asyncio
async def test_forged_signature_and_oversized_token_fail_closed(verifier):
    provider, key = verifier
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert await provider.verify_token(signed(attacker)) is None
    assert await provider.verify_token("x" * 8193) is None


def test_oauth_requires_https_and_unique_local_policies():
    identity = OAuthClientPolicy(client_id="hermes-client", client_role="writer")
    with pytest.raises(TokenConfigurationError, match="HTTPS"):
        JWKSClientVerifier(issuer="http://login.example.test", audience="https://memory.example.test/mcp",
                           jwks_url="https://login.example.test/jwks", identities=[identity])
    with pytest.raises(TokenConfigurationError, match="unique"):
        JWKSClientVerifier(issuer="https://login.example.test", audience="https://memory.example.test/mcp",
                           jwks_url="https://login.example.test/jwks", identities=[identity, identity])


@pytest.mark.asyncio
async def test_oauth_identity_reaches_http_mcp_policy(verifier, tmp_path):
    provider, key = verifier
    service = MemoryService(tmp_path / "oauth.db")
    server = create_server(service, token_verifier=provider,
                           public_url="https://memory.example.test/mcp")
    app = server.streamable_http_app()
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://127.0.0.1:8000") as anonymous:
                assert (await anonymous.post("/mcp", content=b"{}")).status_code == 401
                for bad_token in (
                    signed(key, aud="https://other.example.test/mcp"),
                    signed(key, exp=1),
                    signed(rsa.generate_private_key(public_exponent=65537, key_size=2048)),
                ):
                    denied = await anonymous.post("/mcp", content=b"{}",
                                                  headers={"Authorization": "Bearer " + bad_token})
                    assert denied.status_code == 401
            async with httpx.AsyncClient(transport=transport,
                    base_url="http://127.0.0.1:8000",
                    headers={"Authorization": "Bearer " + signed(key)}) as client:
                async with streamable_http_client("http://127.0.0.1:8000/mcp", http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        created = await session.call_tool("memory_add", {
                            "project_id": "alpha", "memory_type": "fact",
                            "content": "OAuth identity owns this pending fact",
                        })
                        assert not created.isError
                        import json
                        record = json.loads(created.content[0].text)
                        assert record["client_id"] == "hermes-client"
                        assert record["status"] == "pending"
    finally:
        service.close()
