import importlib


_BACKEND_CACHE = {}


def _backend_order(persistent_profile: bool):
    if persistent_profile:
        return (
            ("patchright", "patchright.sync_api"),
            ("playwright", "playwright.sync_api"),
            ("rebrowser-playwright", "rebrowser_playwright.sync_api"),
        )
    return (
        ("rebrowser-playwright", "rebrowser_playwright.sync_api"),
        ("patchright", "patchright.sync_api"),
        ("playwright", "playwright.sync_api"),
    )


def get_backend(*, persistent_profile: bool = False):
    cache_key = "persistent_profile" if persistent_profile else "default"
    if cache_key in _BACKEND_CACHE:
        return _BACKEND_CACHE[cache_key]

    last_error = None
    for backend_name, module_name in _backend_order(persistent_profile):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover
            last_error = exc
            continue
        result = (backend_name, module.sync_playwright, module.TimeoutError)
        _BACKEND_CACHE[cache_key] = result
        return result

    raise ImportError("No Playwright backend available") from last_error


BACKEND_NAME, sync_playwright, PlaywrightTimeoutError = get_backend()
PERSISTENT_PROFILE_BACKEND_NAME, persistent_profile_sync_playwright, PersistentProfileTimeoutError = get_backend(
    persistent_profile=True
)
