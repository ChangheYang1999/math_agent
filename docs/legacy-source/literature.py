"""Safe, project-scoped downloads for direct open-access PDF URLs."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from .config import Config
from .paths import Paths

_MAX_REDIRECTS = 5
_CHUNK_SIZE = 64 * 1024


class DownloadError(ValueError):
    """Raised when a remote resource fails a download safety check."""


@dataclass(frozen=True)
class DownloadResult:
    relative_path: str
    sha256: str
    size_bytes: int
    url: str


@dataclass(frozen=True)
class _ValidatedTarget:
    pinned_url: str
    host_header: str
    sni_hostname: str


class PDFDownloader:
    def __init__(
        self,
        paths: Paths,
        config: Config,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.paths = paths
        self.config = config
        self._client = client

    async def download(self, url: str, filename_hint: str | None = None) -> DownloadResult:
        """Download a public HTTP(S) PDF into the content-addressed paper store."""
        del filename_hint  # Content addressing is stable across model-provided title variants.
        timeout_seconds = float(self.config.runtime.timeout_seconds)
        try:
            if self._client is not None:
                return await asyncio.wait_for(
                    self._download_with_client(self._client, url), timeout=timeout_seconds
                )

            timeout = httpx.Timeout(timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                return await asyncio.wait_for(
                    self._download_with_client(client, url), timeout=timeout_seconds
                )
        except TimeoutError:
            raise DownloadError("PDF request timed out") from None

    async def _download_with_client(self, client: httpx.AsyncClient, url: str) -> DownloadResult:
        original_url = url
        current_url = url
        response: httpx.Response | None = None

        for redirect_count in range(_MAX_REDIRECTS + 1):
            target = await _validate_public_url(current_url)
            try:
                response_context = client.stream(
                    "GET",
                    target.pinned_url,
                    headers={"Host": target.host_header},
                    follow_redirects=False,
                    auth=None,
                    extensions={"sni_hostname": target.sni_hostname},
                )
                async with response_context as candidate:
                    if candidate.is_redirect:
                        location = candidate.headers.get("location")
                        if not location:
                            raise DownloadError("Redirect response has no destination")
                        if redirect_count == _MAX_REDIRECTS:
                            raise DownloadError("PDF URL exceeded the redirect limit")
                        current_url = urljoin(current_url, location)
                        continue
                    response = candidate
                    response.raise_for_status()
                    return await self._store_response(response, original_url)
            except DownloadError:
                raise
            except (httpx.HTTPError, TimeoutError) as exc:
                raise DownloadError("PDF request failed") from exc

        raise DownloadError("PDF URL exceeded the redirect limit")

    async def _store_response(self, response: httpx.Response, original_url: str) -> DownloadResult:
        maximum = int(self.config.limits.max_pdf_mb * 1024 * 1024)
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError as exc:
                raise DownloadError("PDF response has an invalid declared size") from exc
            if declared_size < 0:
                raise DownloadError("PDF response has an invalid declared size")
            if declared_size > maximum:
                raise DownloadError("PDF exceeds the configured size limit")

        content = bytearray()
        digest = hashlib.sha256()
        async for chunk in response.aiter_bytes(_CHUNK_SIZE):
            if len(content) + len(chunk) > maximum:
                raise DownloadError("PDF exceeds the configured size limit")
            content.extend(chunk)
            digest.update(chunk)

        if not content.startswith(b"%PDF-"):
            raise DownloadError("Downloaded content does not have a PDF signature")

        checksum = digest.hexdigest()
        relative_path = f"literature/papers/{checksum}.pdf"
        try:
            self.paths.write_immutable(relative_path, bytes(content))
        except FileExistsError:
            existing = self.paths.resolve(relative_path).read_bytes()
            if hashlib.sha256(existing).hexdigest() != checksum:
                raise DownloadError("Existing content-addressed PDF has unexpected bytes") from None

        return DownloadResult(
            relative_path=relative_path,
            sha256=checksum,
            size_bytes=len(content),
            url=original_url,
        )


async def _validate_public_url(url: str) -> _ValidatedTarget:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise DownloadError("Invalid PDF URL") from exc

    if parsed.scheme not in {"http", "https"}:
        raise DownloadError("PDF URL must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise DownloadError("PDF URL must not contain credentials")
    if not parsed.hostname:
        raise DownloadError("PDF URL must include a host")

    host = parsed.hostname
    logical_url = httpx.URL(url)
    sni_hostname = logical_url.raw_host.decode("ascii")
    host_header = logical_url.netloc.decode("ascii")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise DownloadError("PDF URL host must be a public address")
        return _ValidatedTarget(str(logical_url), host_header, sni_hostname)

    effective_port = port or (443 if parsed.scheme == "https" else 80)
    try:
        results = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            effective_port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise DownloadError("PDF URL host could not be resolved") from exc
    if not results:
        raise DownloadError("PDF URL host could not be resolved")
    try:
        addresses = [ipaddress.ip_address(item[4][0]) for item in results]
    except ValueError as exc:
        raise DownloadError("PDF URL host returned an invalid address") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise DownloadError("PDF URL host must resolve only to public addresses")
    pinned_url = logical_url.copy_with(host=addresses[0].compressed)
    return _ValidatedTarget(str(pinned_url), host_header, sni_hostname)
