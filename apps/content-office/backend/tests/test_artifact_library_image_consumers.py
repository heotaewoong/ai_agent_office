import copy

import pytest
from PIL import Image

from office.blog_assets import collect_assets, verify_manifest
from office.media import artifact_record
from office.store import Store, WorkflowError, digest
from office.thumbnail_studio import (
    attach_to_manifest,
    candidate_path,
    choose,
    generate,
    production_candidates,
    snapshot,
)


@pytest.fixture
def artwork(tmp_path):
    store = Store(tmp_path / 'state')
    job = store.create_job({'id': 'image-consumer-test', 'title': '합성 이미지 시험'})
    job = store.save_source(job['id'], {
        'title': '합성 이미지 시험', 'body': '합성 시험 원고입니다.',
        'quality': {'status': 'passed', 'critical': []}, 'synthetic_fixture': True,
        'video': {'scenes': [{'narration': '합성 시험', 'caption': '합성 시험'}]},
    })
    folder = store.artifacts / job['id'] / job['source_hash'] / 'thumbnail-studio'
    folder.mkdir(parents=True)
    candidates = []
    for index in range(3):
        candidate = {'id': f'candidate-{index}', 'title': '합성 시험', 'angle': '합성 구도'}
        for kind, size in [('image', (1280, 720)), ('portrait', (1080, 1920)), ('artwork', (64, 64))]:
            path = folder / f'{kind}-{index}.png'
            Image.new('RGB', size, (index * 60, 40, 80)).save(path)
            candidate[kind] = artifact_record(store.artifacts, path)
        candidates.append(candidate)
    state = {'source_hash': job['source_hash'], 'title': '합성 시험', 'candidates': candidates,
             'selected_id': candidates[0]['id'], 'selected_format': 'landscape'}
    store.update_job(job['id'], thumbnail_studio=state)
    return store, store.job(job['id']), candidates


def trash(store, *records):
    store.set_setting('artifact_library', {'entries': {
        'synthetic-trash': {'state': 'trash', 'paths': [record['path'] for record in records]},
    }})


@pytest.mark.parametrize('kind', ['image', 'portrait', 'artwork'])
def test_thumbnail_path_blocks_trashed_bytes_until_restored(artwork, kind):
    store, job, candidates = artwork
    candidate = candidates[0]
    record = candidate[kind]
    path = store.artifacts / record['path']
    original = path.read_bytes()
    trash(store, record)
    with pytest.raises(WorkflowError, match='휴지통'):
        candidate_path(store, job['thumbnail_studio'], candidate, kind)
    assert path.read_bytes() == original
    store.set_setting('artifact_library', {'entries': {}})
    assert candidate_path(store, job['thumbnail_studio'], candidate, kind).read_bytes() == original


@pytest.mark.parametrize('finalize', [False, True])
def test_thumbnail_choice_rejects_trash_without_changing_job_or_approval(artwork, finalize):
    store, job, candidates = artwork
    trash(store, candidates[0]['image'])
    before = store.job(job['id'])
    with pytest.raises(WorkflowError, match='휴지통'):
        choose(store, job['id'], candidates[0]['id'], snapshot(store, job['id'])['revision'], finalize=finalize)
    assert store.job(job['id']) == before


def test_thumbnail_edit_rejects_trashed_reference_before_provider_creation(artwork):
    store, job, candidates = artwork
    trash(store, candidates[0]['artwork'])
    before = store.job(job['id'])

    def no_provider(*args, **kwargs):
        pytest.fail('A trashed reference must be rejected before creating a provider')

    with pytest.raises(WorkflowError, match='휴지통'):
        generate(store, job['id'], job['source_hash'], edit_id=candidates[0]['id'],
                 instruction='빛만 바꾸기', provider_factory=no_provider)
    assert store.job(job['id']) == before


def test_cached_thumbnail_generation_does_not_return_trashed_candidates(artwork):
    store, job, candidates = artwork
    trash(store, candidates[1]['image'])
    with pytest.raises(WorkflowError, match='휴지통'):
        generate(store, job['id'], job['source_hash'])


@pytest.mark.parametrize('consumer', ['production', 'manifest'])
def test_thumbnail_reuse_rejects_trash_without_changing_manifest(artwork, tmp_path, consumer):
    store, job, candidates = artwork
    store.review_source(job['id'], job['source_hash'], 'approved', 'synthetic', {'video': True})
    trash(store, candidates[0]['portrait' if consumer == 'production' else 'image'])
    before = store.job(job['id'])
    manifest = {'source_hash': job['source_hash'], 'files': [], 'hash': 'unchanged'}
    original = copy.deepcopy(manifest)
    with pytest.raises(WorkflowError, match='휴지통'):
        if consumer == 'production':
            production_candidates(store, job['id'], tmp_path)
        else:
            attach_to_manifest(store, job['id'], manifest)
    assert manifest == original
    assert store.job(job['id']) == before


def test_finalizing_available_thumbnail_cannot_reattach_trashed_sibling(artwork):
    store, job, candidates = artwork
    store.update_job(job['id'], manifest={
        'source_hash': job['source_hash'], 'completed_outputs': ['video'], 'files': [], 'hash': 'unchanged',
    }, release_approval={'decision': 'approved'})
    trash(store, candidates[1]['image'])
    before = store.job(job['id'])
    with pytest.raises(WorkflowError, match='휴지통'):
        choose(store, job['id'], candidates[0]['id'], snapshot(store, job['id'])['revision'], finalize=True)
    assert store.job(job['id']) == before


@pytest.fixture
def blog_cards(artwork):
    store, job, _ = artwork
    folder = store.artifacts / job['id'] / job['source_hash'] / 'cards'
    folder.mkdir()
    slides = []
    for index in range(6):
        path = folder / f'card-{index + 1:02}.png'
        Image.new('RGB', (64, 64), (index * 30, 20, 40)).save(path)
        slides.append({'index': index + 1, 'title': '합성 카드', 'artifact': artifact_record(store.artifacts, path)})
    store.update_job(job['id'], cards={
        'source_hash': job['source_hash'], 'checks': {'passed': True}, 'slides': slides,
    })
    output = folder.parent / 'blog-output'
    output.mkdir()
    return store, store.job(job['id']), output


def test_blog_does_not_copy_trashed_current_card_into_new_export(blog_cards):
    store, job, output = blog_cards
    trash(store, job['cards']['slides'][0]['artifact'])
    before = store.job(job['id'])
    with pytest.raises(WorkflowError, match='휴지통'):
        collect_assets(store, job, output)
    assert not (output / 'blog-image-01.png').exists()
    assert store.job(job['id']) == before


@pytest.mark.parametrize('trashed', ['metadata', 'image'])
def test_blog_manifest_verification_rejects_trashed_export_files(blog_cards, trashed):
    store, job, output = blog_cards
    _, paths, _ = collect_assets(store, job, output)
    records = [{**artifact_record(store.artifacts, path), 'outputs': ['blog']} for path in paths]
    manifest = {'source_hash': job['source_hash'], 'files': records}
    verify_manifest(store, job, manifest)
    record = next(record for record in records if
                  record['name'] == ('blog-assets.json' if trashed == 'metadata' else 'blog-image-01.png'))
    trash(store, record)
    before = digest(manifest)
    with pytest.raises(WorkflowError, match='휴지통'):
        verify_manifest(store, job, manifest)
    assert digest(manifest) == before
