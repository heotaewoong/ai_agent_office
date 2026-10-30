import pytest
from fastapi.testclient import TestClient
from office.api import create_app
from office.owned_source import extract_tistory,preview_tistory,create_owned_job
from office.store import Store,WorkflowError

BODY='내가 작성한 원문입니다. 업무 흐름을 확인하고 직접 검토할 내용을 정리합니다. '*8

def test_tistory_preserves_text_photo_table_code_and_ignores_scripts():
    result=extract_tistory('<meta property="og:title" content="내 글"><header>메뉴</header><div class="contents_style"><h2>제목</h2><p>'+BODY+'</p><img src="https://blog.kakaocdn.net/photo.png" alt="사진"><table><tr><th>조건</th><th>행동</th></tr><tr><td>검토</td><td>확인</td></tr></table><pre><code>print(123)</code></pre><script>공격 지시</script></div>')
    assert result['title']=='내 글' and result['image_count']==1
    assert '## 제목' in result['body'] and '![사진](https://blog.kakaocdn.net/photo.png)' in result['body']
    assert '| 조건 | 행동 |' in result['body'] and 'print(123)' in result['body']
    assert '공격 지시' not in result['body'] and '메뉴' not in result['body']

@pytest.mark.parametrize('url',['http://x.tistory.com/x','https://localhost/x','https://x.tistory.com.evil.test/x','https://x.tistory.com:8443/x','https://user:secret@x.tistory.com/x','https://127.0.0.1/x'])
def test_disallowed_import_never_fetches(monkeypatch,url):
    monkeypatch.setattr('office.owned_source.fetch_public',lambda *a,**k:pytest.fail('must not fetch'))
    with pytest.raises(WorkflowError):preview_tistory(url)

def test_no_body_and_oversized_body_fail_without_silent_truncation():
    with pytest.raises(WorkflowError):extract_tistory('<p>로그인 화면</p>')
    with pytest.raises(WorkflowError):extract_tistory('<div class="contents_style">'+'글'*50001+'</div>')

def test_original_job_is_unapproved_idempotent_and_never_queues_paid_work(tmp_path):
    store=Store(tmp_path)
    a=create_owned_job(store,'제목',BODY)
    b=create_owned_job(store,'제목',BODY)
    assert a['id']==b['id']
    assert a['source_packet']['body']==BODY
    assert a['source_packet']['preserve_original'] is True
    assert a['source_approval'] is None and store.tasks()==[]

def test_api_ownership_and_csrf_guards(tmp_path):
    client=TestClient(create_app(Store(tmp_path)),base_url='http://localhost:8510')
    data={'title':'제목','body':BODY,'owner_confirmed':True}
    assert client.post('/api/owned-source/jobs',json=data).status_code==403
    csrf=client.get('/api/session').json()['csrf']
    headers={'Origin':'http://localhost:3110','X-Office-CSRF':csrf}
    assert client.post('/api/owned-source/jobs',json={**data,'owner_confirmed':False},headers=headers).status_code==409
    response=client.post('/api/owned-source/jobs',json=data,headers=headers)
    assert response.status_code==200 and response.json()['source_approval'] is None
