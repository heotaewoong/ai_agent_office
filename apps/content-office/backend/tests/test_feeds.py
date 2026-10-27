from datetime import datetime, timezone
import pytest
from office.feeds import parse_feed, rank_articles, normalize_url, validate_public_url

NOW = datetime(2026, 10, 25, 18, tzinfo=timezone.utc)
FEED = {"id": "test", "name": "Test feed", "url": "https://example.com/rss"}


def test_rss_dates_duplicates_and_future_are_distinguished():
    xml = '''<rss><channel><item><title>Agent workflow</title><link>https://example.com/a?utm_source=rss</link><pubDate>Sat, 24 Oct 2026 10:00:00 GMT</pubDate><description>Useful agent</description></item><item><title>Undated</title><link>https://example.com/b</link></item><item><title>Future</title><link>https://example.com/c</link><pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'''
    articles = parse_feed(xml, FEED, NOW)
    ranked = rank_articles(articles, NOW)
    assert len(articles) == 3
    assert [a["title"] for a in ranked] == ["Agent workflow"]
    assert articles[1]["published_at"] is None
    assert articles[2]["date_status"] == "future"


def test_atom_rfc3339_and_namespaces_parse():
    xml = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>AI update</title><link rel="alternate" href="https://example.com/a"/><published>2026-10-24T09:00:00+09:00</published><summary>New model</summary></entry></feed>'''
    articles = parse_feed(xml, FEED, NOW)
    assert articles[0]["published_at"] == "2026-10-24T00:00:00+00:00"
    assert articles[0]["feed_name"] == "Test feed"


def test_same_article_tracking_url_is_deduplicated():
    one = {"id": "a", "title": "AI agent", "url": "https://example.com/a?utm_source=rss", "published_at": "2026-10-24T10:00:00+00:00", "summary": "agent code", "feed_name": "official", "date_status": "valid"}
    two = {**one, "id": "b", "url": "https://example.com/a/"}
    assert len(rank_articles([one, two], NOW)) == 1
    assert normalize_url(one["url"]) == normalize_url(two["url"])


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "https://localhost/x", "file:///tmp/x", "https://169.254.169.254/x", "https://[::1]/x", "https://user:pass@example.com/"])
def test_private_network_and_credential_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_entity_expansion_is_rejected():
    with pytest.raises(ValueError):
        parse_feed('<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel/></rss>', FEED, NOW)


def test_html_doctype_in_cdata_code_example_is_not_an_xml_entity_declaration():
    xml = '''<rss><channel><item><title>Agent coding guide</title><link>https://example.com/coding</link><pubDate>Sat, 24 Oct 2026 10:00:00 GMT</pubDate><description><![CDATA[An HTML example: <!DOCTYPE html><html><body>Example</body></html>]]></description></item></channel></rss>'''
    rows = parse_feed(xml, FEED, NOW)
    assert len(rows) == 1
    assert rows[0]['title'] == 'Agent coding guide'


def test_same_event_title_on_different_urls_is_one_candidate():
    one = {"id": "a", "title": "Introducing a new AI agent workflow", "url": "https://example.com/a", "published_at": "2026-10-24T10:00:00+00:00", "summary": "agent code", "feed_name": "official", "date_status": "valid"}
    two = {**one, "id": "b", "url": "https://example.org/b"}
    assert len(rank_articles([one, two], NOW)) == 1


def test_generic_or_distant_titles_do_not_hide_distinct_news_events():
    from office.feeds import deduplicate_events
    def article(identity, title, date):
        return {"id": identity, "title": title, "url": "https://example.com/" + identity, "published_at": date, "score": 70}
    generic = [article("a", "AI update", "2026-10-24T10:00:00+00:00"), article("b", "AI update", "2026-10-24T11:00:00+00:00")]
    separate_days = [article("c", "A detailed weekly agent workflow roundup", "2026-10-20T10:00:00+00:00"), article("d", "A detailed weekly agent workflow roundup", "2026-10-24T10:00:00+00:00")]
    assert len(deduplicate_events(generic)) == 2
    assert len(deduplicate_events(separate_days)) == 2
    assert len(deduplicate_events([{**item, "event_id": "curated-event"} for item in separate_days])) == 1
