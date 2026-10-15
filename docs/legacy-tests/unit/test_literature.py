import asyncio
import hashlib
import socket

import httpx
import pytest

from math_research_agent.config import Config
from math_research_agent.literature import DownloadError, PDFDownloader
from math_research_agent.paths import Paths

PUBLIC_DNS = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: PUBLIC_DNS)


@pytest.mark.asyncio
async def test_download_streams_a_pdf_to_a_content_addressed_project_path(
    tmp_path, public_dns
) -> None:
    payload = b"%PDF-1.7\nopen access paper"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") is None
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "papers.example"
        assert request.extensions["sni_hostname"] == "papers.example"
        return httpx.Response(200, content=payload, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await PDFDownloader(Paths(tmp_path), Config(), client).download(
            "https://papers.example/article.pdf", "../../Unsafe Paper Name"
        )
    finally:
        await client.aclose()

    digest = hashlib.sha256(payload).hexdigest()
    assert result.relative_path == f"literature/papers/{digest}.pdf"
    assert result.sha256 == digest
    assert result.size_bytes == len(payload)
    assert result.url == "https://papers.example/article.pdf"
    assert (tmp_path / result.relative_path).read_bytes() == payload


@pytest.mark.asyncio
async def test_download_deduplicates_identical_pdf_bytes(tmp_path, public_dns) -> None:
    payload = b"%PDF-1.4\nthe same paper"
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, content=payload, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    downloader = PDFDownloader(Paths(tmp_path), Config(), client)
    try:
        first = await downloader.download("https://one.example/paper.pdf")
        second = await downloader.download("https://two.example/copy.pdf")
    finally:
        await client.aclose()

    assert requests == 2
    assert second.relative_path == first.relative_path
    assert len(list((tmp_path / "literature/papers").glob("*.pdf"))) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/paper.pdf",
        "https://user:password@example.com/paper.pdf",
        "http://127.0.0.1/paper.pdf",
        "http://[::1]/paper.pdf",
    ],
)
async def test_download_rejects_non_http_credentials_and_private_literal_hosts(
    tmp_path, url
) -> None:
    async def should_not_run(request: httpx.Request) -> httpx.Response:
        raise AssertionError("blocked URLs must not reach the HTTP transport")

    client = httpx.AsyncClient(transport=httpx.MockTransport(should_not_run))
    try:
        with pytest.raises(DownloadError):
            await PDFDownloader(Paths(tmp_path), Config(), client).download(url)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_download_rejects_a_hostname_resolving_to_a_private_address(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.7", 443))
        ],
    )

    async def should_not_run(request: httpx.Request) -> httpx.Response:
        raise AssertionError("private DNS results must be rejected before the request")

    client = httpx.AsyncClient(transport=httpx.MockTransport(should_not_run))
    try:
        with pytest.raises(DownloadError, match="public"):
            await PDFDownloader(Paths(tmp_path), Config(), client).download(
                "https://papers.example/paper.pdf"
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_download_revalidates_redirect_destinations(tmp_path, public_dns) -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DownloadError, match="public"):
            await PDFDownloader(Paths(tmp_path), Config(), client).download(
                "https://papers.example/paper.pdf"
            )
    finally:
        await client.aclose()

    assert seen == ["https://93.184.216.34/paper.pdf"]


@pytest.mark.asyncio
async def test_download_pins_the_validated_address_against_dns_rebinding(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dns_calls = 0

    def rebinding_dns(*args, **kwargs):
        nonlocal dns_calls
        dns_calls += 1
        address = "93.184.216.34" if dns_calls == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", rebinding_dns)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "papers.example"
        assert request.extensions["sni_hostname"] == "papers.example"
        return httpx.Response(200, content=b"%PDF-1.7\npinned", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await PDFDownloader(Paths(tmp_path), Config(), client).download(
            "https://papers.example/paper.pdf"
        )
    finally:
        await client.aclose()

    assert dns_calls == 1


@pytest.mark.asyncio
async def test_relative_redirect_uses_logical_url_and_revalidates_before_repinning(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = iter(("93.184.216.34", "151.101.1.69"))
    dns_calls = 0

    def changing_public_dns(*args, **kwargs):
        nonlocal dns_calls
        dns_calls += 1
        address = next(resolved)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", changing_public_dns)
    seen: list[tuple[str, str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                str(request.url),
                request.headers["host"],
                request.extensions["sni_hostname"],
            )
        )
        if request.url.path == "/papers/start.pdf":
            return httpx.Response(302, headers={"location": "next.pdf"}, request=request)
        return httpx.Response(200, content=b"%PDF-1.7\nredirected", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await PDFDownloader(Paths(tmp_path), Config(), client).download(
            "https://papers.example/papers/start.pdf"
        )
    finally:
        await client.aclose()

    assert dns_calls == 2
    assert seen == [
        ("https://93.184.216.34/papers/start.pdf", "papers.example", "papers.example"),
        ("https://151.101.1.69/papers/next.pdf", "papers.example", "papers.example"),
    ]


@pytest.mark.asyncio
async def test_download_enforces_declared_and_streamed_size_limits(tmp_path, public_dns) -> None:
    limit_bytes = 1024 * 1024

    async def declared_too_large(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": str(limit_bytes + 1)},
            content=b"%PDF-1.7\n",
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(declared_too_large))
    try:
        with pytest.raises(DownloadError, match="size"):
            await PDFDownloader(Paths(tmp_path), Config(limits={"max_pdf_mb": 1}), client).download(
                "https://papers.example/large.pdf"
            )
    finally:
        await client.aclose()

    async def streamed_too_large(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.7\n" + b"x" * limit_bytes,
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(streamed_too_large))
    try:
        with pytest.raises(DownloadError, match="size"):
            await PDFDownloader(Paths(tmp_path), Config(limits={"max_pdf_mb": 1}), client).download(
                "https://papers.example/large.pdf"
            )
    finally:
        await client.aclose()

    assert not (tmp_path / "literature").exists()


@pytest.mark.asyncio
async def test_download_rejects_non_pdf_content_without_writing_it(tmp_path, public_dns) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<!doctype html>paywall", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DownloadError, match="PDF"):
            await PDFDownloader(Paths(tmp_path), Config(), client).download(
                "https://papers.example/not-a-pdf"
            )
    finally:
        await client.aclose()

    assert not (tmp_path / "literature").exists()


@pytest.mark.asyncio
async def test_injected_transport_is_still_bounded_by_runtime_timeout(tmp_path, public_dns) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(2)
        return httpx.Response(200, content=b"%PDF-1.7\nlate", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=None)
    try:
        with pytest.raises(DownloadError, match="timed out"):
            await PDFDownloader(
                Paths(tmp_path), Config(runtime={"timeout_seconds": 1}), client
            ).download("https://papers.example/slow.pdf")
    finally:
        await client.aclose()
