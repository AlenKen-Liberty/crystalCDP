# Crystal CDP

Library-first web content fetcher for internal modules.

It accepts a URL, reuses Chromium cookies when possible, trims page content for downstream LLMs, and auto-upgrades from `http` to `headless` to `headed` when lighter paths fail.

## What It Does

- Primary interface: `from crystal_cdp import Crystal`
- Default egress chain: `WARP -> Mac backup -> direct`
- Cookie reuse from `~/.config/chromium/Default/`
- Optional headed reuse of the real Chromium profile for login-sensitive flows
- HTML cleanup for downstream LLMs
- Browser fallback with headless/headed Chromium
- `rebrowser-playwright` preferred, `patchright` / upstream `playwright` as fallback
- Stealth patches beyond the old canvas-noise approach

## Python Usage

Fetch content:

```python
from crystal_cdp import Crystal

crystal = Crystal()
result = crystal.fetch("https://example.com")

if result.ok:
    print(result.text)
    print(result.links[:5])
else:
    print(result.error)
```

Hold a page for interaction:

```python
from crystal_cdp import Crystal

crystal = Crystal(
    proxy="direct",
    mode="headed",
    auto_upgrade=False,
    use_persistent_profile=True,
)
result = crystal.open("https://voice.google.com/u/0/calls", mode="headed")
page = result.page
```

One-shot CLI remains available for local debugging:

```bash
python3 crystal_cdp.py https://example.com --json
```

## Result Shape

`fetch()` returns a `FetchResult` with:

- `ok`
- `url`
- `text`
- `html`
- `links`
- `mode_used`
- `proxy_used`
- `elapsed_ms`
- `error`
- `attempts`

`open()` returns an `OpenResult` with:

- `ok`
- `url`
- `page`
- `browser`
- `mode_used`
- `proxy_used`
- `elapsed_ms`
- `error`
- `attempts`

## Cookie Strategy

1. Read `~/.config/chromium/Default/Cookies`.
2. Reuse matching cookies for the requested host.
3. If direct SQLite decryption fails, fall back to browser-side export from the Chromium profile.
4. Inject cookies into HTTP headers or browser contexts.
5. For sites that still require richer session state, `use_persistent_profile=True` lets headed mode reuse the live Chromium profile directly.

`cryptography` improves Linux cookie decryption reliability. Without it, browser fallback still works for many cases.

## Browser Backend

The preferred backend is `rebrowser-playwright`, based on the official package description that it is intended as a drop-in replacement for Playwright. This repo still falls back to `patchright`, then upstream `playwright`, so the code can run during migration.

## Stealth Strategy

The old canvas-noise approach was removed. Current stealth focuses on lower-noise, higher-signal patches:

- `navigator.webdriver` removal
- `chrome.runtime` / `chrome.app` presence
- language / plugin / mime-type normalization
- `permissions.query()` patch for notifications
- WebGL vendor / renderer normalization
- resource blocking for images, fonts, media, and common trackers
- real Chromium channel with WebRTC leak-reduction flags

## Files

- `crystal_cdp.py`: orchestrator, dataclasses, library entry, debug CLI
- `playwright_backend.py`: `rebrowser-playwright` first, fallback chain
- `http_engine.py`: curl-backed HTTP fetch path
- `browser.py`: headless/headed browser path
- `cookie_manager.py`: Chromium cookie extraction and cache
- `content_cleaner.py`: HTML trimming and link extraction
- `proxy_manager.py`: WARP / Mac / direct egress chain
- `stealth.py`: status detection, stealth patches, Turnstile solve

## Verification

```bash
python3 -m pytest -q
```
