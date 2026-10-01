"""Safety guards: target validation (SSRF), demo-host check, bot-verification detection, risky actions."""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

from playwright.async_api import Page

from app.config import get_settings


class TargetRejected(ValueError):
    pass


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_demo_target(url: str) -> bool:
    return host_of(url) in {h.lower() for h in get_settings().demo_target_hosts}


async def validate_target_url(url: str) -> str:
    """Reject non-http(s), disallowed hosts, and private/loopback/link-local addresses (SSRF)."""
    settings = get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise TargetRejected("target_url must be an http(s) URL")
    host = parsed.hostname.lower()

    if settings.allowed_target_hosts and host not in {h.lower() for h in settings.allowed_target_hosts}:
        raise TargetRejected(f"host {host} is not in ALLOWED_TARGET_HOSTS")

    if settings.allow_local_targets:
        return url

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or 443)
    except socket.gaierror as e:
        raise TargetRejected(f"cannot resolve host {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise TargetRejected(f"host {host} resolves to a non-public address")
    return url


# ---------------------------------------------------------------- bot verification

_VERIFICATION_JS = """
() => {
  const title = (document.title || '').toLowerCase();
  if (title.includes('just a moment') || title.includes('attention required')) return 'challenge page title';
  const frames = [...document.querySelectorAll('iframe')].map(f => (f.src || '').toLowerCase());
  for (const s of frames) {
    if (s.includes('challenges.cloudflare.com')) return 'cloudflare challenge iframe';
    if (s.includes('recaptcha')) return 'recaptcha iframe';
    if (s.includes('hcaptcha')) return 'hcaptcha iframe';
  }
  if (document.querySelector('.g-recaptcha, .h-captcha, .cf-turnstile, #cf-challenge-running, #challenge-form'))
    return 'captcha widget';
  return null;
}
"""


async def detect_verification(page: Page) -> str | None:
    """Return a reason string if the page is a CAPTCHA / bot challenge. Never attempt to bypass it."""
    try:
        return await page.evaluate(_VERIFICATION_JS)
    except Exception:  # noqa: BLE001 - page may be mid-navigation
        return None


# ---------------------------------------------------------------- risky (irreversible) actions

_RISKY = re.compile(
    r"\b(delete|remove|cancel (?:my )?(?:subscription|account|order)|pay(?: now)?|place order|"
    r"confirm (?:purchase|payment|order)|buy now|transfer|unsubscribe|deactivate)\b",
    re.IGNORECASE,
)


def is_risky_label(label: str) -> bool:
    return bool(_RISKY.search(label or ""))
