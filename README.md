# Crystal CDP

A stealth browser launcher designed to bypass Cloudflare and IP blocking using Patchright (a stealth fork of Playwright) and intelligent proxy rotation.

## Features

- **Stealth Browsing**: Employs `patchright` and custom JavaScript injections (like Canvas noise) to evade bot detection.
- **Cloudflare Turnstile Solver**: Automatically detects and solves Cloudflare challenges.
- **Proxy Rotation**: Verifies and rotates proxies dynamically when direct access fails.
- **Persistent Profiles**: Preserves user logins, cookies, and extensions by using the `Default` browser profile.
- **Detached Execution**: Successful launches detach the browser, allowing the script to exit while you continue working in your VNC environment (`DISPLAY=:1`).

## Architecture

- `crystal_cdp.py`: CLI entry point and main orchestration loop.
- `browser.py`: Manages the Patchright browser lifecycle, navigation, and persistent context.
- `stealth.py`: Handles fingerprint spoofing, status detection, and automatic CAPTCHA solving.
- `proxy_loader.py`: Retrieves and quickly validates proxies from a local proxy pool.

## Installation

Ensure you have Python 3 installed. Install the dependencies using `pip`:

```bash
pip install -r requirements.txt
```

*Note: This tool uses `patchright` instead of standard `playwright`.*

## Usage

Run the tool by providing a target URL:

```bash
# Basic usage
python3 crystal_cdp.py https://perplexity.ai

# Force proxy usage (no direct access attempt)
python3 crystal_cdp.py --proxy-only https://perplexity.ai

# Specify a custom proxy
python3 crystal_cdp.py --proxy http://1.1.1.1:8080 https://perplexity.ai

# Increase timeout or proxy limit
python3 crystal_cdp.py --timeout 45 --max-proxies 10 https://perplexity.ai

# Verbose mode
python3 crystal_cdp.py --verbose https://perplexity.ai
```

### Proxy Pool

The `ProxyLoader` looks for a local proxy pool file at:
`~/scripts/openclaw-tool/proxy/proxy_pool.txt`

Make sure this file is populated and updated to ensure reliable proxy fallbacks.

## Testing

This project uses `pytest` for testing. To run the tests, install the test dependencies and run:

```bash
pip install pytest pytest-mock
pytest tests/
```

## Contributing

- Check `DESIGN.md` for full implementation details.
- Code changes should be verified by running the test suite.
