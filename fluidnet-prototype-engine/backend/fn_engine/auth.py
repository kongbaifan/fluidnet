"""Bearer-token access control.

Running a project or the module bench executes user Python code in Worker processes, which are
separate processes, not an OS sandbox. A server reachable from other machines therefore needs a
token on every API call. Tokens live in a JSON file as SHA-256 hashes only; the secret is shown once.

Scopes: `read` may call GET endpoints and open run streams; `control` may also POST (validate,
solve, start runs, commands, variable writes, module saves).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import threading

SCOPES = ("read", "control")
TOKEN_PREFIX = "fn_"
# Browsers cannot set headers on a WebSocket; they offer the token as a subprotocol instead.
WS_PROTOCOL = "fluidnet.bearer."


def default_token_file() -> Path:
    return Path(os.environ.get("FLUIDNET_TOKEN_FILE") or Path(__file__).resolve().parents[2] / ".runtime" / "tokens.json")


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class TokenStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or default_token_file())
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        return json.loads(self.path.read_text(encoding="utf-8")).get("tokens", [])

    def _save(self, tokens: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"tokens": tokens}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def create(self, name: str, scope: str) -> tuple[dict, str]:
        """New token; returns its public record and the secret, which is not stored."""
        if scope not in SCOPES:
            raise ValueError(f"scope 只能是 {'、'.join(SCOPES)}")
        if not name.strip():
            raise ValueError("令牌名称不能为空")
        secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
        record = {"id": secrets.token_hex(4), "name": name.strip(), "scope": scope, "sha256": _digest(secret),
                  "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with self._lock:
            tokens = self._load()
            tokens.append(record)
            self._save(tokens)
        return public(record), secret

    def list(self) -> list[dict]:
        with self._lock:
            return [public(record) for record in self._load()]

    def revoke(self, token_id: str) -> bool:
        with self._lock:
            tokens = self._load()
            kept = [record for record in tokens if record["id"] != token_id]
            if len(kept) == len(tokens):
                return False
            self._save(kept)
            return True

    def verify(self, secret: str | None) -> dict | None:
        """The token record for `secret`, or None. Compared in constant time against every hash."""
        if not secret:
            return None
        digest = _digest(secret)
        with self._lock:
            match = None
            for record in self._load():
                if hmac.compare_digest(record["sha256"], digest):
                    match = record
            return public(match) if match else None


def public(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "sha256"}


@dataclass
class AuthConfig:
    required: bool = False
    store: TokenStore = field(default_factory=TokenStore)


def is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def resolve_auth(mode: str, host: str, store: TokenStore) -> AuthConfig:
    """`auto` requires tokens when listening beyond loopback; `off` is refused there."""
    if mode not in ("auto", "required", "off"):
        raise ValueError("--auth 只能是 auto、required 或 off")
    local = is_loopback(host)
    if mode == "off" and not local:
        raise ValueError(f"监听 {host} 时不能关闭认证：运行项目会执行用户 Python 代码")
    required = mode == "required" or (mode == "auto" and not local)
    if required and not store.list():
        raise ValueError(f"需要认证但还没有令牌；先执行 python -m fn_engine token create <名称> --scope control"
                         f"（令牌文件 {store.path}）")
    return AuthConfig(required=required, store=store)


def bearer(header: str | None) -> str | None:
    if header and header[:7].lower() == "bearer ":
        return header[7:].strip()
    return None


def websocket_secret(headers) -> tuple[str | None, str | None]:
    """(secret, subprotocol to accept) from an Authorization header or a fluidnet.bearer.* subprotocol."""
    secret = bearer(headers.get("authorization"))
    if secret:
        return secret, None
    for protocol in (headers.get("sec-websocket-protocol") or "").split(","):
        protocol = protocol.strip()
        if protocol.startswith(WS_PROTOCOL):
            return protocol[len(WS_PROTOCOL):], protocol
    return None, None


def allowed(record: dict | None, method: str) -> bool:
    if record is None:
        return False
    return record["scope"] == "control" or method in ("GET", "HEAD")
