"""One read-only review download; this never grants release or publishing rights."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .store import WorkflowError


def build_review_bundle(job: dict, artifacts: Path) -> bytes:
    source_hash = job.get('source_hash')
    manifest = job.get('manifest') or {}
    if not source_hash or manifest.get('source_hash') != source_hash:
        raise WorkflowError('현재 원고와 제작물 버전이 다릅니다')
    records = [('production', record) for record in manifest.get('files', [])]
    cards = job.get('cards') or {}
    issues = list((cards.get('checks') or {}).get('issues') or [])
    if cards and cards.get('source_hash') == source_hash:
        records += [('cards', slide['artifact']) for slide in cards.get('slides', []) if slide.get('artifact')]
    elif cards:
        issues.append('이전 원고의 카드뉴스는 제외했습니다')
    root = artifacts.resolve()
    total, seen = 0, set()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for group, record in records:
            name = record.get('name', '')
            if not name or name in ('.', '..') or '/' in name or '\\' in name:
                raise WorkflowError('검토 파일 이름이 올바르지 않습니다')
            destination = group + '/' + name
            if destination in seen:
                raise WorkflowError('중복 파일 이름이 있어 검토 묶음을 만들지 못했습니다')
            seen.add(destination)
            path = (root / record['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise WorkflowError('검토 파일 경로를 확인해 주세요')
            total += path.stat().st_size
            if total > 64 * 1024 * 1024:
                raise WorkflowError('검토 묶음이 64MB를 넘습니다. 개별 파일을 내려받아 주세요')
            with path.open('rb') as handle:
                data = handle.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise WorkflowError('검토 파일이 변경되었습니다. 새로고침해 주세요')
            archive.writestr(destination, data)
        archive.writestr('REVIEW.json', json.dumps({
            'job_id': job['id'], 'source_hash': source_hash,
            'manifest_hash': manifest.get('hash'), 'purpose': 'review_only',
            'release_granted': False, 'external_published': False,
            'cards_checks': cards.get('checks'), 'issues': issues,
            'next_action': '글·영상·카드를 검토하고 현재 제작물에 대한 출고 승인②를 별도로 진행하세요. 이 ZIP은 출고 승인본이 아닙니다.',
        }, ensure_ascii=False, indent=2))
    return buffer.getvalue()
