import copy
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[2] / 'scripts/slack-office-intake.py'
spec = importlib.util.spec_from_file_location('slack_office_intake', SCRIPT) if SCRIPT.exists() else None
intake = importlib.util.module_from_spec(spec) if spec else None
if spec:
    spec.loader.exec_module(intake)

NOW = 1793643000
ENV = {'HERMES_SESSION_PLATFORM': 'slack', 'HERMES_SESSION_PROFILE': 'lumi',
       'HERMES_SESSION_CHAT_ID': 'C0123456789', 'HERMES_SESSION_CHAT_TYPE': 'group',
       'HERMES_SESSION_THREAD_ID': '1793642999.000001', 'HERMES_SESSION_MESSAGE_ID': '1793642999.000001',
       'HERMES_SESSION_USER_ID': 'U0123456789', 'HERMES_SESSION_SCOPE_ID': 'T0123456789'}
IDENTITY = {'ok': True, 'user_id': 'U0987654321', 'team_id': 'T0123456789'}
MESSAGE = {'ts': ENV['HERMES_SESSION_MESSAGE_ID'], 'user': ENV['HERMES_SESSION_USER_ID'],
           'text': '<@U0987654321> 협업으로 자료를 검토해 줘.', 'thread_ts': ENV['HERMES_SESSION_THREAD_ID']}


def verified():
    assert intake is not None, 'bounded Slack intake helper must exist'
    return intake.verify_message(intake.context(ENV), IDENTITY, copy.deepcopy(MESSAGE), {'U0123456789'}, NOW)


@pytest.fixture(autouse=True)
def shared_protocol(monkeypatch):
    from office import assistant_request_protocol
    monkeypatch.setattr(intake, 'protocol_module', lambda: assistant_request_protocol)


@pytest.mark.parametrize('module', ['argparse', 'hashlib'])
def test_unisolated_script_refuses_before_pythonpath_code_import(tmp_path, module):
    marker = 'UNTRUSTED_IMPORT_REACHED'
    (tmp_path / (module + '.py')).write_text("print('" + marker + "'); raise RuntimeError('AUDIT_ONLY')", encoding='utf-8')
    env = {**os.environ, 'PYTHONPATH':str(tmp_path)}
    rejected = subprocess.run([sys.executable,str(SCRIPT),'inspect'],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10)
    assert rejected.returncode == 1
    assert marker not in rejected.stdout + rejected.stderr
    assert json.loads(rejected.stdout) == {'ok':False,'error':{'code':'isolated_runtime_required'}}
    # -I ignores the injected search path before importing any helper dependencies.
    isolated = subprocess.run([sys.executable,'-I','-B',str(SCRIPT),'--help'],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10)
    assert isolated.returncode == 0 and marker not in isolated.stdout + isolated.stderr


def test_verified_current_owner_uses_stable_event_uuid_and_original_text():
    value = verified()
    assert value['text'] == '협업으로 자료를 검토해 줘.'
    assert value['text_hash'] == hashlib.sha256(MESSAGE['text'].encode()).hexdigest()
    assert value['request_id'] == verified()['request_id']
    changed = dict(ENV, HERMES_SESSION_MESSAGE_ID='1793642998.000001', HERMES_SESSION_THREAD_ID='1793642998.000001')
    message = dict(MESSAGE, ts=changed['HERMES_SESSION_MESSAGE_ID'], thread_ts=changed['HERMES_SESSION_THREAD_ID'])
    assert intake.verify_message(intake.context(changed), IDENTITY, message, {'U0123456789'}, NOW)['request_id'] != value['request_id']


@pytest.mark.parametrize('key,value', [('HERMES_SESSION_PLATFORM','api_server'), ('HERMES_SESSION_PROFILE','ada'),
    ('HERMES_SESSION_MESSAGE_ID',''), ('HERMES_SESSION_SCOPE_ID',''), ('HERMES_SESSION_CHAT_ID','https://foreign.test'),
    ('HERMES_CRON_SESSION','1')])
def test_unbound_or_wrong_profile_origin_fails_closed(key, value):
    assert intake is not None, 'bounded Slack intake helper must exist'
    with pytest.raises(intake.IntakeError): intake.context({**ENV, key:value})


@pytest.mark.parametrize('patch', [{'user':'U0999999999'}, {'bot_id':'B0123456789'}, {'subtype':'bot_message'},
    {'edited':{'ts':'1793642999.000001'}}, {'files':[{}]}, {'attachments':[{}]}, {'thread_ts':'1793642900.000001'},
    {'ts':'1793642998.000001'}, {'text':''}, {'text':'x'*4001}])
def test_foreign_bot_edited_attachment_or_mismatched_message_is_not_admitted(patch):
    assert intake is not None, 'bounded Slack intake helper must exist'
    with pytest.raises(intake.IntakeError):
        intake.verify_message(intake.context(ENV), IDENTITY, {**MESSAGE, **patch}, {'U0123456789'}, NOW)


@pytest.mark.parametrize('allowed,identity,now', [({'*'},IDENTITY,NOW), (set(),IDENTITY,NOW),
    ({'U0123456789'},dict(IDENTITY,team_id='T0999999999'),NOW), ({'U0123456789'},IDENTITY,NOW+601),
    ({'U0123456789'},IDENTITY,NOW-32)])
def test_allowlist_workspace_and_freshness_are_required(allowed, identity, now):
    assert intake is not None, 'bounded Slack intake helper must exist'
    with pytest.raises(intake.IntakeError): intake.verify_message(intake.context(ENV), identity, MESSAGE, allowed, now)


@pytest.mark.parametrize('reply', [False, True])
def test_sdk_read_is_bound_to_exact_current_channel_message_and_thread(reply):
    ctx = intake.context(ENV); seen=[]
    if reply: ctx['thread_id']='1793642900.000001'
    class SDK:
        async def auth_test(self): return IDENTITY
        async def conversations_history(self, **kwargs):
            seen.append(('history', kwargs)); return {'ok':True,'messages':[MESSAGE]}
        async def conversations_replies(self, **kwargs):
            seen.append(('replies', kwargs)); return {'ok':True,'messages':[MESSAGE]}
    identity, message = asyncio.run(intake.fetch_message(SDK(),ctx))
    assert identity == IDENTITY and message == MESSAGE
    assert len(seen)==1 and seen[0][0]==('replies' if reply else 'history')
    assert seen[0][1]=={'channel':ctx['chat_id'],'oldest':ctx['message_id'],'latest':ctx['message_id'],
                          'inclusive':True,'limit':100,**({'ts':ctx['thread_id']} if reply else {})}


@pytest.mark.parametrize('data', [{'ok':False,'messages':[MESSAGE]}, {'ok':True,'messages':[]},
                                  {'ok':True,'messages':[MESSAGE,MESSAGE]}])
def test_sdk_missing_failed_or_ambiguous_message_is_never_guessed(data):
    class SDK:
        async def auth_test(self): return IDENTITY
        async def conversations_history(self, **kwargs): return data
    with pytest.raises(intake.IntakeError): asyncio.run(intake.fetch_message(SDK(),intake.context(ENV)))


class Native:
    def __init__(self): self.posts=[]; self.cards=[]; self.lose_ack=False; self.hidden=False
    def board(self): return {'columns':[{'name':'todo','tasks':[] if self.hidden else copy.deepcopy(self.cards)}]}
    def create(self, body):
        self.posts.append(body);card={**body,'id':'t_current','status':'todo'};self.cards.append(card)
        if self.lose_ack: raise OSError('PRIVATE NETWORK DETAIL')
        return {'task':card}


class Office:
    def __init__(self): self.gets=[]
    def lookup(self, rid):
        self.gets.append(rid)
        return {'request_id':rid,'native_task_id':'t_current','board':'heobrain-office','status':'queued','delivery':{'slack':'watching'}}


def test_submit_is_durable_and_same_message_does_not_create_twice(tmp_path):
    value=verified(); office=Office(); native=Native(); state=tmp_path/'watches.json'
    first=intake.submit(value,value['text_hash'],intake.NativeCreator(native,state),office)
    second=intake.submit(value,value['text_hash'],intake.NativeCreator(native,state),office)
    assert first==second and len(native.posts)==1
    assert office.gets==[value['request_id']]*2
    assert not state.exists(), 'separate helper must never overwrite daemon-owned watches'
    assert 'text' not in json.loads(state.with_name('watches.json.admissions.json').read_text())[value['request_id']]


def test_lost_ack_and_restart_are_get_only_even_if_http_record_is_not_visible(tmp_path):
    value=verified(); office=Office();native=Native();native.lose_ack=True;native.hidden=True
    first=intake.submit(value,value['text_hash'],intake.NativeCreator(native,tmp_path/'watches.json'),office)
    second=intake.submit(value,value['text_hash'],intake.NativeCreator(native,tmp_path/'watches.json'),office)
    assert first['status']==second['status']=='admission_unknown' and len(native.posts)==1 and office.gets==[]
    assert second['request_id']==value['request_id']


def test_hash_mismatch_never_creates_a_native_card(tmp_path):
    value=verified();office=Office();native=Native()
    with pytest.raises(intake.IntakeError): intake.submit(value,'0'*64,intake.NativeCreator(native,tmp_path/'watches.json'),office)
    assert native.posts==[] and office.gets==[]


def test_office_lookup_is_get_only_without_auth_or_cookie_overrides():
    assert intake is not None, 'bounded Slack intake helper must exist'
    client=intake.OfficeReader();seen=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,_limit):return json.dumps({'request_id':'test'}).encode()
    client.opener=SimpleNamespace(open=lambda request,timeout:(seen.append(request) or Response()))
    client.lookup(verified()['request_id'])
    assert len(seen)==1 and seen[0].get_method()=='GET'
    assert not any(key.lower() in {'cookie','authorization','x-office-csrf'} for key in seen[0].headers)


def test_receipt_contains_only_safe_metadata_and_exact_deep_link():
    value=verified()
    result=intake.safe_receipt({'request_id':value['request_id'],'native_task_id':'t_current','board':'heobrain-office','status':'queued','body':'PRIVATE'},value['request_id'],'https://office.example')
    assert result['url']=='https://office.example/office3d?assistant_request='+value['request_id']
    assert 'PRIVATE' not in json.dumps(result) and 'body' not in result
