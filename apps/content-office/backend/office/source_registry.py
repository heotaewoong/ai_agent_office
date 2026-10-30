"""Read-only source classification; no network, model call or business-state writes."""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


@lru_cache(maxsize=4)
def load_sources(path=Path(__file__).resolve().parents[1] / 'config/feeds.json'):
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    seen = set()
    for row in rows:
        if row['id'] in seen or row['segment'] not in ('exam', 'ai') or urlsplit(row['url']).scheme != 'https' or not row['name'] or not row['topics'] or not row['language']:
            raise ValueError('Invalid or duplicate source registry entry')
        seen.add(row['id'])
    return rows


def classify_article(article):
    source = next((row for row in load_sources() if row['id'] == article.get('feed_id')), {})
    segment = article.get('segment') if article.get('segment') in ('exam', 'ai') else source.get('segment', 'unclassified')
    return {**article, 'segment': segment, 'topics': article.get('topics') or source.get('topics', []), 'language': article.get('language') or source.get('language', 'unknown')}
