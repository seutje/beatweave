import socket
from urllib.parse import urlsplit, urlunsplit


def connection_url(base_url: str, timeout_seconds: float) -> str:
    """Prefer a reachable IPv4 localhost relay without changing saved URL identity."""
    parsed = urlsplit(base_url)
    if parsed.hostname != "localhost" or parsed.scheme != "http":
        # HTTPS certificates and SNI must retain the configured hostname.
        return base_url
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=min(1, timeout_seconds)):
            pass
    except OSError:
        # Keep IPv6-only localhost services working.
        return base_url
    authority = "127.0.0.1" + (f":{parsed.port}" if parsed.port else "")
    return urlunsplit(parsed._replace(netloc=authority))
