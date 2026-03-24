from content_cleaner import clean_for_llm, extract_links


HTML = """
<html>
  <body>
    <header>Top Nav</header>
    <article>
      <h1>Main Story</h1>
      <p>Hello <a href="/world">world</a></p>
    </article>
    <script>console.log("x")</script>
    <footer>Footer</footer>
  </body>
</html>
"""


def test_clean_for_llm():
    text = clean_for_llm(HTML, "https://example.com/post")
    assert "Main Story" in text
    assert "Hello" in text
    assert "Top Nav" not in text
    assert "console.log" not in text


def test_extract_links():
    links = extract_links(HTML, "https://example.com/post")
    assert links == [{"text": "world", "href": "https://example.com/world"}]
