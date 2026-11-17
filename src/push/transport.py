"""SSRF-safe HTTPS transport for the pywebpush requests-session seam.

No requests proxy/environment inheritance, redirects, second DNS lookup, or
response-body reads. TLS still authenticates the original provider hostname.
"""

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

from requests import ConnectionError, Response

from .models import validate_endpoint


class UnsafeEndpoint(ValueError):
    pass


class DeliveryCancelled(Exception):
    """Consent, session validity or the delivery deadline changed during I/O."""


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, guard=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.guard = guard

    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or len(addresses) > 32:
            raise UnsafeEndpoint("Push provider address unavailable")
        for family, _, _, _, address in addresses:
            ip = ipaddress.ip_address(address[0])
            if family not in (socket.AF_INET, socket.AF_INET6) or not ip.is_global or ip.is_multicast or ip.is_reserved:
                raise UnsafeEndpoint("Push provider address unavailable")
        if self.guard is not None:
            self.guard()
        family, socktype, protocol, _, address = addresses[0]
        raw = socket.socket(family, socktype, protocol)
        try:
            raw.settimeout(self.timeout)
            raw.connect(address)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class PinnedTransport:
    def __init__(self, guard=None):
        self.guard = guard

    def post(self, url, data, headers, timeout):
        try:
            validate_endpoint(url)
        except ValueError:
            raise UnsafeEndpoint("Unsupported push endpoint") from None
        parts = urlsplit(url)
        connection = PinnedHTTPSConnection(
            parts.hostname, timeout=min(float(timeout), 5), context=ssl.create_default_context(), guard=self.guard
        )
        try:
            # DNS and TLS can block. Check consent/deadlines again after both,
            # immediately before emitting the request, and refresh provider TTL.
            connection.connect()
            if self.guard is not None:
                headers = {**headers, "ttl": str(self.guard())}
            target = parts.path + ("?" + parts.query if parts.query else "")
            connection.request("POST", target, body=data, headers={**headers, "Host": parts.hostname})
            upstream = connection.getresponse()
            # No response body, endpoint or request headers are retained in the
            # adapter response or exception. pywebpush reads response.text even
            # with verbose=False, so provide an empty body explicitly.
            response = Response()
            response.status_code = upstream.status
            response._content = b""
            retry = upstream.getheader("Retry-After")
            if retry and len(retry) <= 64:
                response.headers["Retry-After"] = retry
            return response
        except (OSError, http.client.HTTPException):
            raise ConnectionError("Push provider unavailable") from None
        finally:
            connection.close()
