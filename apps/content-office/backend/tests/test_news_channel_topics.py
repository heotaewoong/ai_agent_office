import copy
import pytest
from office.editorial import content_review_checks, REVIEW_SCHEMA
from office.channel_adaptation import adaptation_prompt


def reviews(verdicts):
    return [{'role': role, 'content_checks': {'source_sufficient': True, 'topic_matches': True,
             'reason': '전파망원경 관측이라는 원문 사건을 설명한다', 'channel_topics': copy.deepcopy(verdicts)}}
            for role in ('critique', 'eval')]


@pytest.mark.parametrize('verdicts', [[],
    [{'channel': 'linkedin_personal', 'topic_matches': False, 'reason': '결말이 회의 녹취 자동화로 바뀐다'}],
    [{'channel': 'linkedin_personal', 'topic_matches': True, 'reason': ' '}],
    [{'channel': 'threads_main', 'topic_matches': True, 'reason': '다른 채널만 확인'}],
    [{'channel': 'linkedin_personal', 'topic_matches': True, 'reason': '일치'},
     {'channel': 'linkedin_personal', 'topic_matches': False, 'reason': '업무로 이탈'}]])
def test_body_pass_does_not_hide_missing_or_drifting_social_copy(verdicts):
    packet = {'news_review_required': True, 'channel_posts': {'linkedin_personal': '전파망원경. 업무에도 적용한다. [예시]'}}
    result = content_review_checks({'passed': True, 'issues': []}, packet, reviews(verdicts))
    assert result['passed'] is False
    assert any('linkedin_personal' in issue for issue in result['blocking'])


def test_every_present_social_copy_needs_both_reviewers_and_reasons():
    packet = {'news_review_required': True, 'channel_posts': {'linkedin_personal': '관측', 'threads_main': '관측'}}
    verdicts = [{'channel': key, 'topic_matches': True, 'reason': '원문 관측 과정과 조건을 요약했다'} for key in packet['channel_posts']]
    assert content_review_checks({'passed': True, 'issues': []}, packet, reviews(verdicts))['passed']
    missing = reviews(verdicts); missing[1]['content_checks'].pop('channel_topics')
    assert not content_review_checks({'passed': True, 'issues': []}, packet, missing)['passed']


def test_social_contract_does_not_force_unrelated_workplace_lesson():
    prompt = adaptation_prompt()
    assert '업무에 적용할 교훈' not in prompt
    assert '원문 주제' in prompt
    assert 'channel_topics' in REVIEW_SCHEMA['properties']['content_checks']['required']


def test_news_generation_overrides_the_generic_workplace_story_template(tmp_path):
    import json
    from office.store import Store
    from office.editorial import prepare_source
    class Recorder:
        calls = []
        def generate(self, role, messages, schema, options):
            self.calls.append((role, messages))
            if role in ('gen', 'refine'):
                return {'title': '전파망원경에 AI를 붙인 이유', 'body': '관측 데이터를 보정하고 분석한다.', 'video': {}}
            return {'role': role, 'score': 90, 'passed': True, 'critical_issues': [], 'minor_issues': [], 'summary': '검토',
                    'content_checks': {'source_sufficient': True, 'topic_matches': True, 'reason': '관측 주제와 일치', 'channel_topics': []}}
    store = Store(tmp_path)
    job = store.create_job({'id': 'radio-news', 'title': '전파망원경 관측 AI', 'url': 'https://example.org/radio',
        'origin': 'rss', 'evidence': [{'id': 'E1', 'claim': '관측 데이터를 보정하고 분석한다', 'source_quote': '관측 데이터를 보정하고 분석한다', 'url': 'https://example.org/radio'}]})
    provider = Recorder(); prepare_source(store, job['id'], provider)
    messages = next(messages for role, messages in provider.calls if role == 'gen')
    context = json.loads(messages[1]['content'])
    assert '입력·판단·다음 행동이 모두 보이는 완결 사례' not in context['instructions']
    assert '제공된 뉴스의 원문 사건' in context['instructions']
    assert '충돌하는 audience.problem' in messages[0]['content']
