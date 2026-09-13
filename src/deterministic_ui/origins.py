"""Exact-origin policy. Demo defaults are loopback-only; local file demos are pinned."""
from dataclasses import dataclass
from urllib.parse import urlsplit

from .surface import SurfaceError


def origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise SurfaceError("ORIGIN_NOT_ALLOWED")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{parsed.hostname.lower()}:{port}"


@dataclass(frozen=True)
class OriginPolicy:
    allowed: frozenset[str]
    file_url: str | None = None

    @classmethod
    def for_url(cls, url: str, allowed_origins: frozenset[str] | None = None):
        parsed = urlsplit(url)
        if parsed.scheme == "file" and not parsed.netloc and allowed_origins is None:
            return cls(frozenset(), url.split('#', 1)[0])
        if allowed_origins is None:
            if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise SurfaceError("ORIGIN_NOT_ALLOWED")
            allowed_origins = frozenset({origin(url)})
        policy = cls(frozenset(origin(item) for item in allowed_origins))
        if not policy.permits(url):
            raise SurfaceError("ORIGIN_NOT_ALLOWED")
        return policy

    def permits(self, url: str) -> bool:
        if self.file_url and url.split('#', 1)[0] == self.file_url:
            return True
        try:
            return origin(url) in self.allowed
        except (SurfaceError, ValueError):
            return False
