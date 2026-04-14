"""Playwright-driven browser trajectory recorder.

Hooks the page so that user clicks, key presses, navigation, and scrolls land in the
trajectory log. Uses ARIA role+name as the grounding anchor.

Security-relevant decisions:

- The page→host event channel is gated by a per-session nonce. Page JavaScript
  cannot fabricate trajectory events without the nonce, which is closure-scoped
  inside the init script and never assigned to a window-visible name.
- Secure-field detection happens BOTH at keydown (skip buffering) AND at flush
  time (drop buffer if the field has since become secure or had `password`
  semantics applied via "show password" toggle).
- Screenshots are off by default (`UNDERSTUDY_SCREENSHOTS=0`). When enabled they
  land in the data dir — see README "Threat Model & Limitations" for the gap.
- Cross-origin iframes are skipped: page-level binding only fires from the top
  frame.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Frame,
    Page,
    Playwright,
    async_playwright,
)

from understudy.config import get_settings
from understudy.db import insert_trajectory, session
from understudy.security import is_allowed, redact, url_host
from understudy.types import ActionType, TargetKind, Trajectory, TrajectoryStep

from .aria import aria_ref

log = logging.getLogger(__name__)


def _probe_js(nonce: str) -> str:
    # Nonce is closure-scoped — never written to window/document/dataset.
    return r"""
((NONCE) => {
    if (window.__understudyProbeInstalled) return;
    window.__understudyProbeInstalled = true;

    const send = (payload) => {
        try { window.__understudyEvent(NONCE, JSON.stringify(payload)); } catch (e) {}
    };

    const isSecureEl = (el) => {
        if (!el || el.nodeType !== 1) return false;
        if (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA') return false;
        if (el.type === 'password') return true;
        const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
        if (ac === 'current-password' || ac === 'new-password' || ac === 'one-time-code'
            || ac === 'cc-number' || ac === 'cc-csc' || ac === 'cc-exp') return true;
        if (el.dataset && el.dataset.sensitive) return true;
        return false;
    };

    const describeElement = (el) => {
        if (!el || el.nodeType !== 1) return null;
        const role = el.getAttribute('role') || el.tagName.toLowerCase();
        const name = (el.getAttribute('aria-label')
            || el.getAttribute('alt')
            || el.getAttribute('title')
            || (el.innerText || '').trim().slice(0, 120)
            || el.getAttribute('placeholder')
            || '').trim();
        const path = [];
        let cur = el, depth = 0;
        while (cur && cur.parentElement && depth < 8) {
            const idx = Array.from(cur.parentElement.children).indexOf(cur);
            path.unshift(idx);
            cur = cur.parentElement;
            depth++;
        }
        return { role, name, path, isSecure: isSecureEl(el),
                 tag: el.tagName.toLowerCase(), id: el.id || null };
    };

    document.addEventListener('click', (e) => {
        if (!e.isTrusted) return;
        const d = describeElement(e.target);
        if (!d) return;
        send({ kind: 'click', ts: Date.now(), x: e.clientX, y: e.clientY, target: d });
    }, true);

    document.addEventListener('change', (e) => {
        if (!e.isTrusted) return;
        const d = describeElement(e.target);
        if (!d) return;
        const value = (d.isSecure || isSecureEl(e.target)) ? null : (e.target.value ?? null);
        send({ kind: 'change', ts: Date.now(), target: d, value });
    }, true);

    let typingBuffer = '';
    let typingTarget = null;
    let typingEl = null;
    let typingTimer = null;
    const flushTyping = () => {
        if (typingBuffer && typingTarget && typingEl && !isSecureEl(typingEl)) {
            send({ kind: 'type', ts: Date.now(), target: typingTarget, text: typingBuffer });
        }
        typingBuffer = ''; typingTarget = null; typingEl = null;
    };

    document.addEventListener('keydown', (e) => {
        if (!e.isTrusted) return;
        const el = e.target;
        const d = describeElement(el);
        if (!d) return;
        if (e.key.length > 1 || e.metaKey || e.ctrlKey) {
            flushTyping();
            send({
                kind: 'key', ts: Date.now(), target: d, key: e.key,
                mod: {
                    meta: e.metaKey, ctrl: e.ctrlKey,
                    alt: e.altKey, shift: e.shiftKey,
                }
            });
            return;
        }
        if (isSecureEl(el)) return;
        typingTarget = d; typingEl = el;
        typingBuffer += e.key;
        clearTimeout(typingTimer);
        typingTimer = setTimeout(flushTyping, 350);
    }, true);

    window.addEventListener('beforeunload', flushTyping, true);
    document.addEventListener('paste', (e) => {
        if (!e.isTrusted) return;
        const el = e.target;
        if (isSecureEl(el)) return;
        const d = describeElement(el);
        if (!d) return;
        try {
            const text = (e.clipboardData || window.clipboardData).getData('text');
            if (text) send({ kind: 'type', ts: Date.now(), target: d, text });
        } catch (_) {}
    }, true);
})("__NONCE__");
""".replace("__NONCE__", nonce)


class BrowserRecorder:
    def __init__(self, *, task_name: str, start_url: str, headed: bool = True) -> None:
        self.task_name = task_name
        self.start_url = start_url
        self.headed = headed
        self.trajectory = Trajectory(task_name=task_name, target_kind=TargetKind.BROWSER)
        self._idx = 0
        self._pw: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._stop_event = asyncio.Event()
        self._nonce = secrets.token_urlsafe(32)
        self._screenshots_enabled = os.environ.get("UNDERSTUDY_SCREENSHOTS", "0") == "1"
        # Every origin the browser contacted during capture. Becomes the
        # replay-time egress allowlist. Keep bounded to avoid unbounded growth
        # on a long recording session.
        self._observed_origins: set[str] = set()
        self._origin_cap_warned = False

    @property
    def trajectory_path(self) -> Path:
        s = get_settings()
        return s.trajectories_dir() / f"{self.trajectory.id}.jsonl"

    @property
    def meta_path(self) -> Path:
        s = get_settings()
        return s.trajectories_dir() / f"{self.trajectory.id}.meta.json"

    def _record_origin(self, url: str) -> None:
        """Add a URL's host to the observed-origins set, if it passes allowlist hardening."""
        if len(self._observed_origins) >= 1024:
            if not self._origin_cap_warned:
                log.warning(
                    "origin allowlist cap (1024) reached — further hosts "
                    "from this recording will not be tracked; replay may "
                    "block legitimate requests",
                )
                self._origin_cap_warned = True
            return
        host = url_host(url)
        if host is None:
            return
        if not is_allowed(url):
            return  # deny-listed origins never enter the allowlist
        self._observed_origins.add(host)

    def _next_idx(self) -> int:
        self._idx += 1
        return self._idx

    async def _maybe_screenshot(self, idx: int, kind: str | None) -> Path | None:
        if not self._screenshots_enabled:
            return None
        if kind not in {"click", "nav", "key"}:
            return None
        page = self._page
        if page is None:
            return None
        s = get_settings()
        out = s.trajectories_dir() / f"{self.trajectory.id}_{idx:04d}.png"
        try:
            await page.screenshot(path=str(out), full_page=False)
            with contextlib.suppress(OSError):
                out.chmod(0o600)
            return out
        except Exception as e:
            log.debug("screenshot failed: %s", e)
            return None

    async def _append(self, step: TrajectoryStep) -> None:
        self.trajectory.steps.append(step)
        self.trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trajectory_path.open("a", encoding="utf-8") as f:
            f.write(step.model_dump_json() + "\n")
        with contextlib.suppress(OSError):
            self.trajectory_path.chmod(0o600)

    async def _on_event(self, nonce: str, raw: str) -> None:
        # Page JS cannot forge events without the nonce.
        if not secrets.compare_digest(nonce, self._nonce):
            log.warning("dropped event with bad nonce")
            return
        try:
            evt = json.loads(raw)
        except json.JSONDecodeError:
            return
        page = self._page
        if page is None:
            return
        url = page.url
        if not is_allowed(url):
            log.warning("skipped event on denied domain: %s", url)
            return

        target = evt.get("target") or {}
        kind = evt.get("kind")
        ref = aria_ref(target.get("role"), target.get("name"), target.get("path"))
        idx = self._next_idx()
        screenshot_path = await self._maybe_screenshot(idx, kind)
        text = evt.get("text") or evt.get("value")
        red = redact(text)
        x, y = evt.get("x"), evt.get("y")
        coords: tuple[int, int] | None = None
        if x is not None and y is not None:
            coords = (int(x), int(y))

        step = TrajectoryStep(
            idx=idx,
            action=_map_action(kind),
            url=url,
            selector=_selector_from(target),
            aria_ref=ref,
            aria_role=target.get("role"),
            aria_name=target.get("name"),
            text=red.text or None,
            key=evt.get("key"),
            coords=coords,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            redacted=red.changed,
        )
        await self._append(step)

    async def _on_framenav(self, frame: Frame) -> None:
        if self._page is None or frame is not self._page.main_frame:
            return
        url = frame.url
        if not is_allowed(url):
            log.warning("nav to denied domain, recording placeholder: %s", url)
            url = "[denied]"
        await self._append(
            TrajectoryStep(idx=self._next_idx(), action=ActionType.NAV, url=url),
        )

    async def run(self) -> Trajectory:
        if not is_allowed(self.start_url):
            raise ValueError(f"start_url is on the deny list: {self.start_url}")

        async with async_playwright() as pw:
            self._pw = pw
            browser = await pw.chromium.launch(headless=not self.headed)
            self._context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=False,
            )
            await self._context.add_init_script(_probe_js(self._nonce))
            self._page = await self._context.new_page()

            async def _binding(_source: object, nonce: str, raw: str) -> None:
                await self._on_event(nonce, raw)

            await self._context.expose_binding("__understudyEvent", _binding)

            self._page.on(
                "framenavigated",
                lambda fr: asyncio.create_task(self._on_framenav(fr)),
            )
            self._page.on("close", lambda _: self._stop_event.set())
            self._context.on("close", lambda _: self._stop_event.set())
            # Sub-resource origin tracking: every document, image, script,
            # stylesheet, xhr, fetch, media, and font request passes through
            # here. We record host only; request bodies and URLs are not
            # persisted — only the normalized hostname enters the allowlist.
            self._context.on("request", lambda r: self._record_origin(r.url))
            # WebSocket is a page-level event, not a context event.
            self._page.on("websocket", lambda ws: self._record_origin(ws.url))

            log.info("recording %r → %s", self.task_name, self.trajectory_path)
            await self._page.goto(self.start_url, wait_until="domcontentloaded")
            await self._stop_event.wait()

            from datetime import UTC, datetime

            self.trajectory.finished_at = (
                datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            )
            self.trajectory.allowed_origins = sorted(self._observed_origins)
            self._write_meta_sidecar()

        with session() as conn:
            insert_trajectory(conn, self.trajectory, self.trajectory_path)
        return self.trajectory

    def _write_meta_sidecar(self) -> None:
        """Persist trajectory metadata that doesn't belong in the steps JSONL.

        Extensible; today only carries `allowed_origins`. Loader treats a
        missing sidecar as a legacy recording (empty allowlist → replay falls
        back to nav-derived hosts).
        """
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"allowed_origins": self.trajectory.allowed_origins}
        self.meta_path.write_text(json.dumps(payload), encoding="utf-8")
        with contextlib.suppress(OSError):
            self.meta_path.chmod(0o600)


def _map_action(kind: str | None) -> ActionType:
    match kind:
        case "click":
            return ActionType.CLICK
        case "type":
            return ActionType.TYPE
        case "change":
            return ActionType.SELECT
        case "key":
            return ActionType.KEY
        case "nav":
            return ActionType.NAV
        case _:
            return ActionType.NOTE


def _selector_from(target: dict[str, object]) -> str | None:
    el_id = target.get("id")
    if el_id:
        return f"#{el_id}"
    role = target.get("role")
    name = target.get("name")
    if role and name:
        return f'role={role}[name="{name}"]'
    return None


__all__ = ["BrowserRecorder"]
