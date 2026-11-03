"""Bounded, same-origin HWPX reading for attachment-backed public notices."""
import hashlib
import re
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree
from zipfile import ZipFile

from .store import SourceUnavailable


class NoticeParser(HTMLParser):
    VOID = {'br', 'img', 'input', 'meta', 'link', 'hr', 'source', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.body, self.items = [], [], []
        self.has_panel, self.item = False, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        panel = 'synapTextWrap' in classes or bool(self.stack and self.stack[-1][1])
        attachment = 'attachment' in classes or bool(self.stack and self.stack[-1][2])
        self.has_panel |= 'synapTextWrap' in classes
        if panel and tag in {'p', 'div', 'section', 'br', 'li', 'h1', 'h2', 'h3', 'h4'}:
            self.body.append('\n')
        if attachment and tag == 'li':
            self.item = {'text': [], 'links': []}
        if self.item is not None and tag == 'a' and attrs.get('href'):
            self.item['links'].append(attrs['href'])
        if tag not in self.VOID:
            self.stack.append((tag, panel, attachment))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][1] and tag in {'p', 'div', 'section', 'li', 'h1', 'h2', 'h3', 'h4'}:
            self.body.append('\n')
        if tag == 'li' and self.item is not None:
            self.items.append(self.item)
            self.item = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            self.body.append(data)
        if self.item is not None:
            self.item['text'].append(data)


def hwpx_text(raw):
    if len(raw) > 8_000_000:
        raise ValueError('document too large')
    with ZipFile(BytesIO(raw)) as archive:
        files = archive.infolist()
        if len(files) > 500 or sum(f.file_size for f in files) > 24_000_000:
            raise ValueError('archive too large')
        sections = sorted((f for f in files if re.fullmatch(r'Contents/section\d+\.xml', f.filename)),
                          key=lambda f: int(re.search(r'\d+', f.filename).group()))
        if not 1 <= len(sections) <= 32:
            raise ValueError('missing document sections')
        paragraphs = []
        for record in sections:
            if record.file_size > 4_000_000 or record.flag_bits & 1:
                raise ValueError('invalid section')
            xml = archive.read(record).decode('utf-8')
            if '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper() or '\x00' in xml:
                raise ValueError('external entities forbidden')
            root = ElementTree.fromstring(xml)
            for paragraph in root.iter():
                if paragraph.tag.rsplit('}', 1)[-1] != 'p':
                    continue
                # Avoid repeating table-cell text in its parent paragraph.
                if any(child is not paragraph and child.tag.rsplit('}', 1)[-1] == 'p'
                       for child in paragraph.iter()):
                    continue
                text = ''.join(node.text or '' for node in paragraph.iter()
                               if node.tag.rsplit('}', 1)[-1] == 't').strip()
                if text:
                    paragraphs.append(text)
    return '\n\n'.join(paragraphs)[:60000]


def notice_material(markup, url, title, fetch):
    parser = NoticeParser()
    parser.feed(markup[:2_000_000])
    if not parser.has_panel:
        return None
    body = '\n\n'.join(' '.join(line.split()) for line in ''.join(parser.body).splitlines() if line.strip())
    if len(body.replace(title, '').strip()) >= 200:
        return body, url, []
    origin = urlsplit(url)
    candidates = []
    for item in parser.items:
        label = ' '.join(' '.join(item['text']).split())
        if '.hwpx' not in label.lower():
            continue
        for link in item['links']:
            try:
                target = urlsplit(urljoin(url, link))
                port = target.port
            except ValueError:
                continue
            if (target.scheme == 'https' and target.hostname == origin.hostname
                    and port in (None, 443) and not target.username and not target.password
                    and ('fileDown' in target.path or target.path.lower().endswith('.hwpx'))):
                candidates.append((label, target.geturl()))
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1:
        raise SourceUnavailable('첨부 문서의 실제 본문을 확보하지 못해 원고 생성을 멈췄어요. 공개 원문을 직접 제공해 주세요. 모델 비용은 들지 않았어요')
    name, target = candidates[0]
    try:
        raw, resolved, _ = fetch(target, maximum=8_000_000, allowed_hosts={origin.hostname})
        end = urlsplit(resolved)
        if (end.scheme != 'https' or end.hostname != origin.hostname or end.port not in (None, 443)
                or end.username or end.password):
            raise ValueError('attachment origin changed')
        text = hwpx_text(raw)
        if len(text) < 200:
            raise ValueError('attachment body too short')
    except Exception:
        raise SourceUnavailable('첨부 HWPX 본문을 읽지 못해 원고 생성을 멈췄어요. 공개 원문을 직접 제공해 주세요. 모델 비용은 들지 않았어요') from None
    return text, resolved, [{'url': resolved, 'name': name, 'format': 'hwpx',
                              'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}]
