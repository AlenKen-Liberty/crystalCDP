import html
import re
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin


COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|iframe|svg|canvas|template)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
BOILERPLATE_RE = re.compile(
    r"<(nav|header|footer|aside|form)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
MAIN_CANDIDATE_RE = [
    re.compile(r"<article\b[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<main\b[^>]*>(.*?)</main>", re.IGNORECASE | re.DOTALL),
    re.compile(
        r"<(?:section|div)\b[^>]*(?:id|class)=['\"][^'\"]*"
        r"(content|main|article|post|entry|markdown|body|story)"
        r"[^'\"]*['\"][^>]*>(.*?)</(?:section|div)>",
        re.IGNORECASE | re.DOTALL,
    ),
]
SKIP_LINK_PREFIXES = ("#", "javascript:", "data:", "mailto:", "tel:")


def _strip_tags(fragment: str) -> str:
    return html.unescape(TAG_RE.sub(" ", fragment))


def _normalize_spaces(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()


def _extract_candidate_html(raw_html: str) -> str:
    html_body = SCRIPT_STYLE_RE.sub(" ", raw_html)
    html_body = BOILERPLATE_RE.sub(" ", html_body)
    candidates: List[str] = []
    for pattern in MAIN_CANDIDATE_RE:
        for match in pattern.finditer(html_body):
            fragment = match.group(match.lastindex or 1)
            candidates.append(fragment)
    if not candidates:
        return html_body
    return max(candidates, key=lambda item: len(_strip_tags(item)))


class _StructuredTextParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: List[str] = []
        self.current_href: Optional[str] = None
        self.table_cell_open = False

    def _emit(self, value: str) -> None:
        if not value:
            return
        self.parts.append(value)

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        if tag in {"article", "section", "div", "main", "p", "blockquote"}:
            self._emit("\n")
        elif tag == "br":
            self._emit("\n")
        elif tag == "li":
            self._emit("\n- ")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            self._emit("\n" + ("#" * level) + " ")
        elif tag == "a":
            href = attrs_dict.get("href")
            if href:
                self.current_href = urljoin(self.base_url, href)
        elif tag == "img":
            alt = _normalize_spaces(attrs_dict.get("alt", ""))
            if alt:
                self._emit(f"\n[image: {alt}]")
        elif tag == "tr":
            self._emit("\n")
        elif tag in {"td", "th"}:
            if self.table_cell_open:
                self._emit(" | ")
            self.table_cell_open = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self.current_href = None
        elif tag == "tr":
            self.table_cell_open = False
        elif tag in {"p", "li", "blockquote", "table"}:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        text = _normalize_spaces(data)
        if not text:
            return
        if self.current_href:
            self._emit(f"[{text}]({self.current_href})")
        else:
            self._emit(text + " ")


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str, max_links: int) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.max_links = max_links
        self.current_href: Optional[str] = None
        self.current_text: List[str] = []
        self.links: List[dict] = []
        self.seen: set[tuple[str, str]] = set()

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a" or len(self.links) >= self.max_links:
            return
        href = dict(attrs).get("href")
        if not href:
            return
        if href.lower().startswith(SKIP_LINK_PREFIXES):
            return
        absolute = urljoin(self.base_url, href)
        lowered = absolute.lower()
        if lowered.startswith(SKIP_LINK_PREFIXES):
            return
        self.current_href = absolute
        self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            text = _normalize_spaces(data)
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self.current_href is None:
            return
        text = _normalize_spaces(" ".join(self.current_text))
        entry = (text, self.current_href)
        if self.current_href and entry not in self.seen:
            self.links.append({"text": text or self.current_href, "href": self.current_href})
            self.seen.add(entry)
        self.current_href = None
        self.current_text = []


def _dedupe_lines(text: str) -> str:
    seen_short = set()
    output: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if output and output[-1] != "":
                output.append("")
            continue
        key = line.lower()
        if len(line) <= 80:
            if key in seen_short:
                continue
            seen_short.add(key)
        output.append(line)
    return "\n".join(output).strip()


def clean_for_llm(raw_html: str, base_url: str, max_chars: int = 50000) -> str:
    if not raw_html:
        return ""
    cleaned = COMMENT_RE.sub(" ", raw_html)
    main_html = _extract_candidate_html(cleaned)
    parser = _StructuredTextParser(base_url)
    parser.feed(main_html)
    text = html.unescape("".join(parser.parts))
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    text = _dedupe_lines(text)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[truncated]"
    return text


def extract_links(raw_html: str, base_url: str, max_links: int = 200) -> List[dict]:
    parser = _LinkParser(base_url, max_links=max_links)
    parser.feed(raw_html or "")
    return parser.links
