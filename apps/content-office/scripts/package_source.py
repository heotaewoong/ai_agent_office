#!/usr/bin/env python3
"""Create a private review bundle from an explicit source/evidence allowlist."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]


def sources():
    files = set()
    patterns = [
        'apps/content-office/README.md', 'apps/content-office/docs/*.md',
        'apps/content-office/backend/office/*.py', 'apps/content-office/backend/tests/*.py',
        'apps/content-office/backend/requirements*.txt', 'apps/content-office/backend/config/*.json',
        'apps/content-office/frontend/app/**/*.tsx', 'apps/content-office/frontend/app/**/*.css',
        'apps/content-office/frontend/components/**/*.tsx', 'apps/content-office/frontend/lib/*.ts',
        'apps/content-office/frontend/tests/*.ts', 'apps/content-office/frontend/e2e/*.ts',
        'apps/content-office/frontend/*.json', 'apps/content-office/frontend/*.ts',
        'apps/content-office/frontend/*.md', 'apps/content-office/scripts/*.py', 'apps/content-office/scripts/*.sh',
        'docs/superpowers/plans/2026-10-26-content-office.md', 'docs/superpowers/specs/2026-10-26-content-office-design.md',
        'database/2026-10-26_AI뉴스3선_원고승인대기.md', 'database/2026-10-26_HeoBrain_AI콘텐츠오피스_구현및검증.md',
        'research/content-office-2026-10-26/*-audit.md', 'research/content-office-2026-10-26/*-review.md',
        'research/content-office-2026-10-26/*-resolutions.md', 'research/content-office-2026-10-26/*-experiment.md',
        'research/content-office-2026-10-26/rss-research.md', 'research/content-office-2026-10-26/e2e-report.md',
        'research/content-office-2026-10-26/implementation-verification.json',
        'research/content-office-2026-10-26/window-completion.json',
        'research/content-office-2026-10-26/production-voice-choice.json',
        'research/content-office-2026-10-26/verification-logs/*.txt',
        'apps/content-office/frontend/test-results/production/*.png',
        'apps/content-office/frontend/test-results/production/*.json',
        'research/content-office-2026-10-26/e2e-output/synthetic-short.mp4',
        'research/content-office-2026-10-26/e2e-output/synthetic-captions.srt',
        'research/content-office-2026-10-26/e2e-output/synthetic-voice-*.wav',
        'research/content-office-2026-10-26/e2e-output/synthetic-summary-checklist.pdf',
        'research/content-office-2026-10-26/e2e-output/SAMPLES.md',
    ]
    for pattern in patterns:
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    for path in sorted(files):
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError('Source escaped workspace')
        if path.name in {'credentials.json', '.session-secret', 'secrets.toml', '.env'} or path.name.startswith('.env.'):
            raise ValueError('Credential file excluded: ' + str(path.relative_to(ROOT)))
        yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/HeoBrain_Content_Office_2026-10-26_PRIVATE.zip')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    entries, checksums = [], []
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for path in sources():
            name = path.relative_to(ROOT).as_posix()
            raw = path.read_bytes()
            if path.suffix.lower() in ('.py', '.ts', '.tsx', '.md', '.json', '.sh', '.txt') and re.search(rb'AIza[0-9A-Za-z_-]{35}', raw):
                raise ValueError('Potential credential literal; package stopped at ' + name)
            checksum = hashlib.sha256(raw).hexdigest()
            archive.writestr(name, raw)
            entries.append({'path': name, 'bytes': len(raw), 'sha256': checksum})
            checksums.append(checksum + '  ' + name)
        archive.writestr('SHA256SUMS', '\n'.join(checksums) + '\n')
        archive.writestr('PRIVATE-BUNDLE-NOTES.md', '# 개인 검토용 코드 사본\n\n원본 Markdown111개와 Windows 강의/Marketplace 소스 전체, 실제 DB·키·세션 비밀·모델 캐시·설치한 의존성은 포함하지 않았습니다. 실제 계정 게시·판매 권리 검수 완료를 뜻하지 않습니다. 기존 프로젝트 구조를 보존해 경로를 따라갈 수 있도록 앱 소스·잠금 파일·선택된 검증 기록과 합성 예제를 묶었습니다. 실행법은 apps/content-office/README.md를 읽으세요.\n')
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive CRC verification failed')
        for entry in entries:
            if hashlib.sha256(archive.read(entry['path'])).hexdigest() != entry['sha256']:
                raise ValueError('Archive content verification failed')
    report = {'path': str(args.output), 'files': len(entries), 'bytes': args.output.stat().st_size,
              'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(), 'crc_and_file_hashes_verified': True,
              'credentials_included': False, 'production_database_included': False, 'entries': entries}
    args.output.with_suffix('.manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'entries'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
