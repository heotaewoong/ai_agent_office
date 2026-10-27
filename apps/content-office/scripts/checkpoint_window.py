#!/usr/bin/env python3
"""Read-only foreground checkpoint until the next RSS round, user review, or deadline."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from office.bootstrap import default_store
from office.runtime import aware_time


def inspections(store):
    path = store.root / 'runtime/watch-window.jsonl'
    records = []
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                item = json.loads(line)
                if item.get('kind') == 'inspection_completed':
                    records.append(item)
            except json.JSONDecodeError:
                continue
    return records


def snapshot(store):
    window = store.setting('work_window', {})
    jobs = store.jobs()
    rounds = inspections(store)
    latest = rounds[-1]['report'] if rounds else {}
    feeds = latest.get('rss', {}).get('feeds', [])
    return {'at': datetime.now(timezone.utc).isoformat(), 'window_status': window.get('status'),
            'authorized_end': window.get('authorized_end'), 'rss_rounds': len(rounds),
            'feeds_ok': sum(feed.get('state') == 'ok' for feed in feeds), 'feeds_total': len(feeds),
            'candidates': latest.get('rss', {}).get('eligible_items'),
            'integrity_ok': latest.get('integrity', {}).get('ok'),
            'source_approved': sum(bool(job.get('source_approval', {}).get('decision') == 'approved') for job in jobs if job.get('source_approval')),
            'manifests': sum(bool(job.get('manifest')) for job in jobs),
            'job_states': {job['id']: job['state'] for job in jobs}, 'budget': store.budget()}


def main():
    store = default_store()
    initial = snapshot(store)
    print(json.dumps({'kind': 'checkpoint_started', **initial}, ensure_ascii=False), flush=True)
    end = aware_time(initial['authorized_end'])
    while True:
        current = snapshot(store)
        now = datetime.now(timezone.utc)
        reason = None
        if now >= end:
            reason = 'authorized_deadline_reached'
        elif current['source_approved'] != initial['source_approved'] or current['manifests'] != initial['manifests'] or current['job_states'] != initial['job_states']:
            reason = 'user_review_or_workflow_changed'
        elif current['rss_rounds'] > initial['rss_rounds']:
            reason = 'next_actual_rss_inspection'
        if reason:
            print(json.dumps({'kind': reason, **current}, ensure_ascii=False), flush=True)
            return
        remaining = max(0, (end - now).total_seconds())
        time.sleep(min(60, remaining))
        print(json.dumps({'kind': 'waiting_for_next_inspection_or_user_review', **snapshot(store)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
