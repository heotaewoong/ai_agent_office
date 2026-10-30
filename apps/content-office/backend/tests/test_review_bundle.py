import hashlib
import io
import json
import zipfile
import pytest
from office.review_bundle import build_review_bundle
from office.store import WorkflowError


def fixture(tmp_path):
    data=b'original source asset'
    (tmp_path/'file.txt').write_bytes(data)
    record={'name':'blog.txt','path':'file.txt','sha256':hashlib.sha256(data).hexdigest()}
    job={'id':'job_one','source_hash':'source','manifest':{'source_hash':'source','hash':'manifest','files':[record]},'cards':{'source_hash':'source','checks':{'passed':False,'issues':['2번 65자']},'slides':[{'artifact':{**record,'name':'card.png'}}]}}
    return job


def test_review_contains_all_current_assets_and_visible_issues_without_approval(tmp_path):
    job=fixture(tmp_path)
    with zipfile.ZipFile(io.BytesIO(build_review_bundle(job,tmp_path))) as z:
        assert set(z.namelist())=={'production/blog.txt','cards/card.png','REVIEW.json'}
        note=json.loads(z.read('REVIEW.json'))
        assert note['issues']==['2번 65자']
        assert note['release_granted'] is False and note['external_published'] is False
    assert 'release_approval' not in job


def test_stale_cards_are_excluded_and_reported(tmp_path):
    job=fixture(tmp_path);job['cards']['source_hash']='old'
    with zipfile.ZipFile(io.BytesIO(build_review_bundle(job,tmp_path))) as z:
        assert 'cards/card.png' not in z.namelist()
        assert len(json.loads(z.read('REVIEW.json'))['issues'])==2


def test_api_download_is_review_only_and_does_not_write_job(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from office.api import create_app
    from office.store import Store
    store=Store(tmp_path)
    job=fixture(store.artifacts)
    before=json.dumps(job,sort_keys=True)
    monkeypatch.setattr(store,'require_source_approval',lambda job_id:job)
    client=TestClient(create_app(store),base_url='http://localhost:8510')
    response=client.get('/api/jobs/job_one/review-package')
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert json.loads(z.read('REVIEW.json'))['purpose']=='review_only'
    assert json.dumps(job,sort_keys=True)==before


@pytest.mark.parametrize('case',['manifest','hash','path','name','duplicate','large'])
def test_changed_unsafe_or_oversized_assets_fail_closed(tmp_path,case):
    job=fixture(tmp_path);record=job['manifest']['files'][0]
    if case=='manifest':job['manifest']['source_hash']='old'
    elif case=='hash':record['sha256']='wrong'
    elif case=='path':record['path']='../outside'
    elif case=='name':record['name']='../escape'
    elif case=='duplicate':job['manifest']['files'].append(dict(record))
    elif case=='large':
        with (tmp_path/'file.txt').open('wb') as f:f.truncate(64*1024*1024+1)
    with pytest.raises(WorkflowError):build_review_bundle(job,tmp_path)
