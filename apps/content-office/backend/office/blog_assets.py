"""Package current-source card art and the owner's finalized thumbnail into blog exports."""
import hashlib,json,re
from .store import WorkflowError,digest

NAME_PATTERN=re.compile(r'blog-image-\d{2}\.png')


def dependencies(job):
    source=job.get('source_hash');cards=job.get('cards') or {};thumb=job.get('thumbnail_studio') or {}
    return {'source_hash':source,'cards':cards if cards.get('source_hash')==source else None,
            'thumbnail':thumb if thumb.get('source_hash')==source else None}


def collect_assets(store,job,folder):
    source=job['source_hash'];root=store.artifacts.resolve();images=[];paths=[];warnings=[]
    def copy_image(record,name,alt,kind):
        try:
            path=(root/record['path']).resolve();relative=path.relative_to(root)
            if relative.parts[:2]!=(job['id'],source) or not path.is_file() or path.stat().st_size>8*1024*1024:raise ValueError()
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=record.get('sha256'):raise ValueError()
            from PIL import Image
            with Image.open(path) as image:
                if image.format!='PNG':raise ValueError()
                image.verify()
            target=folder/name
            if target.exists() and target.read_bytes()!=data:raise ValueError()
            if not target.exists():target.write_bytes(data)
        except (OSError,ValueError,KeyError):
            raise WorkflowError('블로그 재사용 이미지의 원고·파일·SHA를 확인하지 못했습니다') from None
        images.append({'name':name,'alt':str(alt),'kind':kind,'sha256':record['sha256'],'source_asset_id':record.get('id')});paths.append(target)
    thumb=job.get('thumbnail_studio') or {};final=thumb.get('finalized_id')
    if thumb.get('source_hash')==source and final and final==thumb.get('selected_id'):
        candidate=next((c for c in thumb.get('candidates',[]) if c.get('id')==final),None)
        if not candidate:raise WorkflowError('확정 썸네일을 찾지 못했습니다')
        from .thumbnail_studio import image_kind,candidate_path
        kind=image_kind(thumb.get('finalized_format') or thumb.get('selected_format') or 'landscape')
        candidate_path(store,thumb,candidate,kind)
        copy_image(candidate[kind],'blog-image-00.png',job['source_packet']['title'],'thumbnail')
    else:warnings.append('같은 원고의 최종 확정 썸네일이 없어 블로그 표지를 자동 선택하지 않았습니다')
    cards=job.get('cards') or {}
    if cards.get('source_hash')==source and (cards.get('checks') or {}).get('passed') is True:
        slides=cards.get('slides') or []
        if not 6<=len(slides)<=8:raise WorkflowError('현재 원고 카드 6~8장을 확인하세요')
        seen=set()
        for i,slide in enumerate(slides,1):
            record=slide.get('artifact') or {}
            if record.get('sha256') in seen:raise WorkflowError('블로그 카드 이미지가 중복됐습니다')
            seen.add(record.get('sha256'))
            copy_image(record,f'blog-image-{i:02}.png',f"카드뉴스 {i}장 · {slide.get('title') or job['source_packet']['title']}",'card')
    else:warnings.append('같은 원고의 검사 통과 카드가 없어 이전 카드를 블로그에 넣지 않았습니다')
    meta={'version':1,'source_hash':source,'dependency_hash':digest(dependencies(job)),'images':images,'warnings':warnings}
    path=folder/'blog-assets.json';path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8');paths.append(path)
    return images,paths,meta


def compose_body(body,images):
    def line(row):
        if not NAME_PATTERN.fullmatch(row['name']):raise WorkflowError('블로그 이미지 이름이 유효하지 않습니다')
        alt=re.sub(r'[\[\]\r\n]', ' ',row['alt'])
        return f"![{alt}]({row['name']})"
    cover=[line(r) for r in images if r['kind']=='thumbnail'];cards=[line(r) for r in images if r['kind']=='card']
    return ('\n\n'.join(cover)+'\n\n' if cover else '')+body+('\n\n## 카드로 다시 보는 핵심 내용\n\n'+'\n\n'.join(cards) if cards else '')


def verify_manifest(store,job,manifest):
    record=next((r for r in manifest.get('files',[]) if r.get('name')=='blog-assets.json' and 'blog' in r.get('outputs',[])),None)
    if record is None:return
    try:
        path=(store.artifacts/record['path']).resolve();relative=path.relative_to(store.artifacts.resolve());data=path.read_bytes()
        if relative.parts[:2]!=(job['id'],job['source_hash']) or hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError()
        metadata=json.loads(data)
        if metadata['source_hash']!=job['source_hash'] or metadata['dependency_hash']!=digest(dependencies(job)):raise ValueError()
        for image in metadata['images']:
            matches=[r for r in manifest.get('files',[]) if r.get('name')==image['name'] and 'blog' in r.get('outputs',[])]
            if len(matches)!=1 or not NAME_PATTERN.fullmatch(image['name']):raise ValueError()
            asset=matches[0];asset_path=(store.artifacts/asset['path']).resolve()
            if asset_path.parent!=path.parent or asset_path.name!=image['name'] or asset.get('sha256')!=image['sha256'] or hashlib.sha256(asset_path.read_bytes()).hexdigest()!=image['sha256']:raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):
        raise WorkflowError('블로그 이미지·선택이 변경되었습니다. 합본을 다시 제작·검토하세요') from None
