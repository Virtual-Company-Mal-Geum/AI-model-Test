"""Shared conversion logic for evaluator gateway inputs."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

from .classification.document_type import classify_document
from .config import Settings
from .crawler import fetch_rendered_html
from .extraction.dom_content import (
    extract_html_metadata,
    extract_json_ld,
    extract_named_sections,
    visible_text,
)
from .extraction.main_content import extract_main_content
from .formatting.html_text import format_html_text
from .models import ExtractedDocument

VALID_DOMAINS = frozenset({"news", "education", "ecommerce", "tech_blog", "None"})


def assert_safe_public_url(url: str) -> None:
    """Block obvious SSRF targets before a browser is allowed to fetch a URL."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain user credentials")

    hostname = parsed.hostname
    if hostname.lower() == "localhost":
        raise ValueError("localhost is not allowed")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved") from exc

    try:
        is_public = all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError as exc:
        raise ValueError("URL hostname resolved to an invalid address") from exc
    if not addresses or not is_public:
        raise ValueError("private, loopback, or non-public network targets are not allowed")


async def prepare_gateway_input(
    context: Any,
    *,
    url: str,
    domain: str,
    settings: Settings,
) -> dict[str, Any]:
    """Render one public page and return exactly the evaluator gateway payload."""
    if domain not in VALID_DOMAINS:
        raise ValueError(f"Unsupported domain: {domain}")
    await asyncio.to_thread(assert_safe_public_url, url)

    raw_html = await fetch_rendered_html(context, url, settings)
    page_text = visible_text(raw_html)
    json_ld = extract_json_ld(raw_html)
    document_type, _ = classify_document(domain, json_ld, page_text)
    metadata = extract_html_metadata(raw_html)
    main_content, _ = extract_main_content(raw_html)
    document = ExtractedDocument(
        document_type=document_type,
        main_content=main_content,
        sections=extract_named_sections(raw_html),
        **metadata,
    )
    return {
        "url": url,
        "domain": domain,
        "html_text": format_html_text(document),
        # Always an array. No JSON-LD is represented as [] rather than "[]".
        "json_ld": json_ld,
    }

