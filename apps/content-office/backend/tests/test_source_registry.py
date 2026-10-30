import json
import pytest
from office.source_registry import classify_article, load_sources


def test_existing_articles_are_classified_without_mutating_saved_records():
    row = {'id': 'one', 'feed_id': 'nvidia', 'title': '시험 AI'}
    assert classify_article(row)['segment'] == 'ai'
    assert 'segment' not in row
    assert classify_article({'feed_id': 'unknown', 'title': 'AI exam'})['segment'] == 'unclassified'
    assert classify_article({'segment': 'exam', 'feed_id': 'nvidia'})['segment'] == 'exam'


def test_registry_has_explicit_language_topics_and_unique_https_sources(tmp_path):
    rows = load_sources()
    assert len(rows) == 11
    assert all(row['segment'] in ('ai', 'exam') and row['language'] in ('en','ko') and row['topics'] for row in rows)
    path = tmp_path / 'feeds.json'
    path.write_text(json.dumps(rows + rows[:1]), encoding='utf-8')
    with pytest.raises(ValueError):
        load_sources(path)


def test_dashboard_adds_source_metadata_without_rewriting_saved_articles(tmp_path):
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient
    from office.store import Store
    from office.api import create_app
    store = Store(tmp_path)
    row = {'id': 'one', 'feed_id': 'nvidia', 'feed_name': 'NVIDIA', 'title': 'Test agent release', 'url': 'https://example.com/news', 'published_at': datetime.now(timezone.utc).isoformat(), 'score': 50}
    store.save_articles([row])
    client = TestClient(create_app(store), base_url='http://localhost:8510')
    result = client.get('/api/dashboard?compact=true')
    assert result.status_code == 200
    body = result.json()
    assert body['articles'][0]['segment'] == 'ai'
    assert len(body['source_registry']) == 11
    assert store.articles_list()[0] == row


def test_busy_ai_sources_cannot_starve_exam_notices():
    from office.source_registry import visible_articles
    rows=[{'id':str(i),'segment':'ai'} for i in range(90)]+[{'id':'exam','segment':'exam'}]
    visible=visible_articles(rows)
    assert len(visible)==80
    assert any(row['id']=='exam' for row in visible)
    assert visible[0]['id']=='0'
