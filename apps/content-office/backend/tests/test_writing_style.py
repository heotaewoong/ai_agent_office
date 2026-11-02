"""The selected writing policy reuses existing calls and cannot edit stored originals."""
from copy import deepcopy

from office.editorial import review_until_ready
from office.writing_style import POLICY_ID


class ReviewProvider:
    def __init__(self, refine=False):
        self.calls = []
        self.refine = refine

    def generate(self, role, messages, schema, options=None):
        self.calls.append((role, messages[0]['content']))
        if role == 'refine':
            return {'body': '모델이 원문 대신 쓴 내용', 'title': '제목', 'video': {'scenes': []}}
        return {'score': 50 if self.refine else 95, 'passed': not self.refine,
                'critical_issues': [], 'minor_issues': [], 'summary': '검토', 'corrections': []}


def test_selected_policy_reuses_existing_review_calls_without_mutating_input():
    provider = ReviewProvider()
    packet = {'title': '제목', 'body': '원문의 주장 50%와 한계를 보존합니다.', 'evidence': []}
    before = deepcopy(packet)
    result = review_until_ready(packet, provider, brief={'language': 'ko'})
    assert [role for role, _ in provider.calls] == ['critique', 'eval', 'korean']
    assert POLICY_ID in provider.calls[-1][1]
    assert all(POLICY_ID not in prompt for _, prompt in provider.calls[:2])
    assert result['quality']['korean']['writing_policy'] == POLICY_ID
    assert packet == before and result['body'] == before['body']


def test_english_review_and_refine_do_not_receive_korean_writing_policy():
    provider = ReviewProvider(refine=True)
    result = review_until_ready({'title': 'Title', 'body': 'Original.', 'evidence': []},
                                provider, brief={'language': 'en'}, refine_limit=1)
    assert 'refine' in [role for role, _ in provider.calls]
    assert all(POLICY_ID not in prompt for _, prompt in provider.calls)
    assert result['quality']['korean']['writing_policy'] is None


def test_original_body_survives_refinement_and_preservation_instruction_has_priority():
    provider = ReviewProvider(refine=True)
    original = '## 저자의 문체\n\n50% 할인 예정입니다.  \n\n| 표 | 보존 |\n|---|---|'
    packet = {'title': '제목', 'body': original, 'evidence': [], 'preserve_original': True}
    result = review_until_ready(packet, provider, brief={'language': 'ko'},
                                original_markdown=original, refine_limit=1)
    assert result['body'] == original and packet['body'] == original
    prompts = [prompt for role, prompt in provider.calls if role in ('korean', 'refine')]
    assert all(POLICY_ID in prompt for prompt in prompts)
    assert all(prompt.index(POLICY_ID) < prompt.index('원문 보존 모드다') for prompt in prompts)
    assert [role for role, _ in provider.calls] == ['critique', 'eval', 'korean', 'refine', 'critique', 'eval', 'korean']
