import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from stealth import PageStatus, detect_html_status, make_google_referer


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class HttpAttemptResult:
    ok: bool
    status: PageStatus
    final_url: str
    html: str
    status_code: Optional[int]
    headers: Dict[str, str]
    error: Optional[str] = None


class HttpEngine:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def fetch(
        self,
        url: str,
        *,
        proxy: Optional[str] = None,
        timeout_ms: int = 15000,
        cookie_header: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        referer: bool = True,
    ) -> HttpAttemptResult:
        curl_path = shutil.which("curl")
        if not curl_path:
            return HttpAttemptResult(
                ok=False,
                status=PageStatus.ERROR,
                final_url=url,
                html="",
                status_code=None,
                headers={},
                error="curl_not_installed",
            )

        headers = dict(DEFAULT_HEADERS)
        if extra_headers:
            headers.update(extra_headers)

        with tempfile.TemporaryDirectory(prefix="crystal-http-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            body_path = tmp_path / "body.bin"
            header_path = tmp_path / "headers.txt"
            args: List[str] = [
                curl_path,
                "-sS",
                "-L",
                "--compressed",
                "--connect-timeout",
                str(max(2, int(timeout_ms / 1000))),
                "--max-time",
                str(max(3, int(timeout_ms / 1000))),
                "--output",
                str(body_path),
                "--dump-header",
                str(header_path),
                "--write-out",
                "__CRYSTAL_META__%{http_code}\t%{url_effective}\t%{content_type}",
            ]
            if proxy:
                args.extend(["--proxy", proxy])
            if referer:
                args.extend(["--referer", make_google_referer(url)])
            if cookie_header:
                args.extend(["--header", f"Cookie: {cookie_header}"])
            for key, value in headers.items():
                args.extend(["--header", f"{key}: {value}"])
            args.append(url)

            try:
                completed = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                return HttpAttemptResult(
                    ok=False,
                    status=PageStatus.ERROR,
                    final_url=url,
                    html="",
                    status_code=None,
                    headers={},
                    error=str(exc),
                )

            meta_line = (completed.stdout or "").strip()
            if completed.returncode != 0 and not meta_line:
                error = (completed.stderr or "").strip() or f"curl_exit_{completed.returncode}"
                status = PageStatus.TIMEOUT if "timed out" in error.lower() else PageStatus.ERROR
                return HttpAttemptResult(
                    ok=False,
                    status=status,
                    final_url=url,
                    html="",
                    status_code=None,
                    headers={},
                    error=error,
                )

            status_code, final_url, content_type = self._parse_meta(meta_line, url)
            response_headers = self._read_headers(header_path)
            if content_type:
                response_headers.setdefault("content-type", content_type)
            html = body_path.read_text(encoding="utf-8", errors="ignore") if body_path.exists() else ""
            status = detect_html_status(
                html=html,
                url=final_url,
                status_code=status_code,
                content_type=response_headers.get("content-type"),
            )
            return HttpAttemptResult(
                ok=status == PageStatus.SUCCESS,
                status=status,
                final_url=final_url,
                html=html,
                status_code=status_code,
                headers=response_headers,
                error=None if status == PageStatus.SUCCESS else completed.stderr.strip() or None,
            )

    def _parse_meta(self, meta_line: str, requested_url: str) -> tuple[Optional[int], str, Optional[str]]:
        if not meta_line.startswith("__CRYSTAL_META__"):
            return None, requested_url, None
        payload = meta_line.replace("__CRYSTAL_META__", "", 1)
        parts = payload.split("\t")
        if len(parts) != 3:
            return None, requested_url, None
        status_code = None
        try:
            status_code = int(parts[0])
        except ValueError:
            status_code = None
        final_url = parts[1] or requested_url
        content_type = parts[2] or None
        return status_code, final_url, content_type

    def _read_headers(self, header_path: Path) -> Dict[str, str]:
        if not header_path.exists():
            return {}
        raw_text = header_path.read_text(encoding="utf-8", errors="ignore")
        blocks = [block.strip() for block in raw_text.split("\r\n\r\n") if block.strip()]
        if len(blocks) == 1 and "\n\n" in raw_text:
            blocks = [block.strip() for block in raw_text.split("\n\n") if block.strip()]
        header_block = blocks[-1] if blocks else raw_text
        headers: Dict[str, str] = {}
        for line in header_block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        return headers
