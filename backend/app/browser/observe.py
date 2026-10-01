"""Turn a live page into a compact, LLM-friendly observation with a numbered element menu."""

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.async_api import Page

MAX_ELEMENTS = 40
MAX_TEXT_CHARS = 1200

# Tags every visible, enabled interactive element with data-mimic-id=N and returns page facts.
_OBSERVE_JS = """
(maxEls) => {
  const SEL = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=checkbox], summary, [onclick]';
  document.querySelectorAll('[data-mimic-id]').forEach(e => e.removeAttribute('data-mimic-id'));
  const visible = el => {
    if (el.closest('[hidden]')) return false;
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const clean = t => (t || '').replace(/\\s+/g, ' ').trim();
  const visibleText = el => clean(el.innerText || el.value || '');
  const labelOf = el => {
    if (el.labels && el.labels.length) return clean(el.labels[0].innerText);
    const aria = el.getAttribute('aria-label'); if (aria) return clean(aria);
    const by = el.getAttribute('aria-labelledby');
    if (by) { const l = document.getElementById(by); if (l) return clean(l.innerText); }
    const t = visibleText(el); if (t) return t.slice(0, 80);
    const img = el.querySelector('img[alt]'); if (img) return clean(img.alt);
    return clean(el.getAttribute('title') || el.getAttribute('placeholder') || el.getAttribute('name') || '');
  };
  const els = []; let i = 0;
  for (const el of document.querySelectorAll(SEL)) {
    if (i >= maxEls) break;
    if (!visible(el) || el.disabled) continue;
    el.setAttribute('data-mimic-id', String(i));
    const r = el.getBoundingClientRect();
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const isText = tag === 'textarea' || (tag === 'input' && !['checkbox','radio','submit','button'].includes(type));
    els.push({
      id: i, tag, type,
      role: el.getAttribute('role') || '',
      label: labelOf(el),
      has_visible_text: !!(visibleText(el) || (el.labels && el.labels.length)),
      value: isText ? (el.value || '') : null,
      placeholder: el.getAttribute('placeholder') || '',
      checked: (type === 'checkbox' || type === 'radio') ? el.checked : null,
      href: tag === 'a' ? (el.getAttribute('href') || '') : '',
      options: tag === 'select' ? [...el.options].map(o => clean(o.text)).slice(0, 10) : null,
      below_fold: r.top >= window.innerHeight,
    });
    i++;
  }
  const headings = [...document.querySelectorAll('h1, h2, h3')].filter(visible).map(h => clean(h.innerText)).filter(Boolean).slice(0, 8);
  const alerts = [...document.querySelectorAll('[role=alert], [role=status], .error, [aria-live]')]
    .filter(visible).map(e => clean(e.innerText)).filter(Boolean).slice(0, 5);
  return { title: document.title || '', headings, alerts, text: clean(document.body ? document.body.innerText : ''), elements: els };
}
"""


@dataclass
class Element:
    id: int
    tag: str
    type: str
    role: str
    label: str
    has_visible_text: bool
    value: str | None
    placeholder: str
    checked: bool | None
    href: str
    options: list[str] | None
    below_fold: bool
    risky: bool = False

    @property
    def kind(self) -> str:
        if self.tag == "a" or self.role == "link":
            return "link"
        if self.tag == "button" or self.role == "button" or self.type in ("submit", "button"):
            return "button"
        if self.type in ("checkbox", "radio") or self.role == "checkbox":
            return self.type or "checkbox"
        if self.tag == "select":
            return "select"
        if self.tag in ("input", "textarea"):
            return f"input[{self.type or 'text'}]"
        return self.tag

    def render(self) -> str:
        parts = [f"[{self.id}] {self.kind} \"{self.label}\""]
        if self.value is not None:
            parts.append(f'value="{self.value[:40]}"')
        if self.checked is not None:
            parts.append("checked" if self.checked else "unchecked")
        if self.options:
            parts.append("options=" + "|".join(self.options))
        if self.below_fold:
            parts.append("(below the fold)")
        if self.risky:
            parts.append("[RISKY: blocked]")
        return " ".join(parts)


@dataclass
class Observation:
    url: str
    title: str
    headings: list[str]
    alerts: list[str]
    text: str
    elements: list[Element] = field(default_factory=list)
    page_hash: str = ""

    @property
    def path(self) -> str:
        return normalize_path(self.url)

    def element(self, element_id: int | None) -> Element | None:
        return next((e for e in self.elements if e.id == element_id), None)

    def to_prompt(self, *, labels_only: bool = False, max_text: int = MAX_TEXT_CHARS) -> str:
        """Compact text for the decision LLM. labels_only hides elements without visible text (low-literacy policy)."""
        els = [e for e in self.elements if e.has_visible_text or not labels_only]
        lines = [f"URL: {self.path}", f"TITLE: {self.title}"]
        if self.headings:
            lines.append("HEADINGS: " + " | ".join(self.headings))
        if self.alerts:
            lines.append("MESSAGES ON PAGE: " + " | ".join(self.alerts))
        text = self.text if len(self.text) <= max_text else self.text[:max_text] + " …(more text below)"
        lines.append(f"PAGE TEXT: {text}")
        lines.append("ELEMENTS:")
        lines.extend(e.render() for e in els)
        if not els:
            lines.append("(no interactive elements on this page; you can still scroll or go back)")
        return "\n".join(lines)

    def summary(self) -> str:
        return f"{self.path} · {self.title} · {len(self.elements)} elements" + (f" · alerts: {self.alerts}" if self.alerts else "")


def normalize_path(url: str) -> str:
    p = urlparse(url)
    path = re.sub(r"/index\.html$", "/", p.path or "/")
    return path


async def observe(page: Page, *, demo_target: bool) -> Observation:
    from app.browser.guards import is_risky_label

    raw = await page.evaluate(_OBSERVE_JS, MAX_ELEMENTS)
    elements = [Element(**e) for e in raw["elements"]]
    if not demo_target:
        for e in elements:
            e.risky = e.kind in ("button", "link", "input[submit]") and is_risky_label(e.label)
    sig = "|".join([page.url, *raw["alerts"], *(f"{e.label}:{e.value}:{e.checked}" for e in elements)])
    return Observation(
        url=page.url,
        title=raw["title"],
        headings=raw["headings"],
        alerts=raw["alerts"],
        text=raw["text"],
        elements=elements,
        page_hash=hashlib.sha1(sig.encode()).hexdigest()[:12],
    )


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1
