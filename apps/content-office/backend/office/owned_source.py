"""Owner supplied text or a public Tistory article. Import is never approval."""
import re
import hashlib
from html.parser import HTMLParser
from urllib.parse import urlsplit
from .feeds import fetch_public
from .store import WorkflowError, digest, now


class ArticleTree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root=['root',{},[]];self.stack=[self.root];self.nodes=0;self.title=''
    def handle_starttag(self,tag,attrs):
        self.nodes+=1
        if self.nodes>30000 or len(self.stack)>100:
            raise WorkflowError('글 구조가 너무 복잡합니다. 원문을 직접 붙여 넣어 주세요')
        node=[tag,dict(attrs),[]];self.stack[-1][2].append(node)
        if tag not in {'area','br','hr','img','input','link','meta','source','wbr'}:self.stack.append(node)
        if tag=='meta' and dict(attrs).get('property')=='og:title':self.title=dict(attrs).get('content','')
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i][0]==tag:del self.stack[i:];break
    def handle_data(self,value):self.stack[-1][2].append(value)


def _image(url):
    try:
        p=urlsplit(url)
        return p.scheme=='https' and p.hostname in {'blog.kakaocdn.net','t1.daumcdn.net'} and not p.username and not p.password and p.port in (None,443) and not any(c in url for c in '\r\n()')
    except ValueError:return False


def _markdown(node):
    if isinstance(node,str):return node
    tag,attrs,children=node
    if tag in {'script','style','form','nav','footer','header','button','noscript','iframe'}:return ''
    inner=''.join(_markdown(n) for n in children)
    if tag=='img':
        src=attrs.get('src') or attrs.get('data-src','')
        return '\n\n!['+attrs.get('alt','원문 사진').replace(']','')+']('+src+')\n\n' if _image(src) else '\n[원문 이미지 주소를 확인해 주세요]\n'
    if tag=='pre':
        fence='`'*max(4,max((len(s) for s in re.findall(r'`+',inner)),default=0)+1)
        return '\n\n'+fence+'\n'+inner.strip('\n')+'\n'+fence+'\n\n'
    if tag=='code':return inner
    if re.fullmatch('h[1-6]',tag):return '\n\n'+'#'*int(tag[1])+' '+inner.strip()+'\n\n'
    if tag in {'th','td'}:return re.sub(r'\s+',' ',inner).replace('|','\\|').strip()+' | '
    if tag=='tr':return '| '+inner.strip()+'\n'
    if tag=='table':
        rows=[line for line in inner.splitlines() if line.strip().startswith('|')]
        if rows:rows.insert(1,'| '+' | '.join('---' for _ in range(rows[0].count('|')-1))+' |')
        return '\n\n'+'\n'.join(rows)+'\n\n'
    if tag=='li':return '\n- '+inner.strip()+'\n'
    if tag=='a':
        url=attrs.get('href','')
        return '['+inner.strip()+']('+url+')' if url.startswith('https://') and not any(c in url for c in '\r\n()') else inner
    if tag=='br':return '\n'
    if tag in {'p','div','section','blockquote','figure','figcaption','ul','ol'}:return '\n\n'+inner.strip()+'\n\n'
    return inner


def extract_tistory(markup):
    parser=ArticleTree();parser.feed(markup)
    candidates=[]
    def find(node):
        if isinstance(node,str):return
        classes=set((node[1].get('class') or '').split())
        priority=max((score for name,score in [('contents_style',1),('article_rep_desc',2),('blogview_content',2),('tt_article_useless_p_margin',3)] if name in classes),default=0)
        if priority:candidates.append((priority,node))
        for child in node[2]:
            find(child)
    find(parser.root)
    article=max(candidates,key=lambda item:item[0])[1] if candidates else None
    if article is None:raise WorkflowError('공개 글 본문을 찾지 못했습니다. 로그인 글은 직접 붙여 넣어 주세요')
    body=re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+','\n\n',_markdown(article)).strip()
    if not 100<=len(body)<=50000:raise WorkflowError('본문은 100~50,000자로 확인해 주세요. 긴 글은 직접 나누어 등록하세요')
    return {'title':parser.title[:200] or '가져온 티스토리 원고','body':body,'image_count':body.count('!['),'status':'needs_review'}


def preview_tistory(url):
    try:
        p=urlsplit(url);host=p.hostname or ''
        if p.scheme!='https' or not re.fullmatch(r'[a-zA-Z0-9-]+\.tistory\.com',host) or host in {'www.tistory.com','notice.tistory.com'} or p.username or p.password or p.port not in (None,443):raise ValueError()
        data,resolved,kind=fetch_public(url,maximum=2_000_000,allowed_hosts={host})
        if 'text/html' not in kind:raise ValueError()
        return {**extract_tistory(data.decode('utf-8')),'source_url':resolved,'html_sha256':hashlib.sha256(data).hexdigest()}
    except WorkflowError:raise
    except Exception:raise WorkflowError('티스토리 공개 글을 가져오지 못했습니다. 원문을 직접 붙여 넣어 주세요') from None


def create_owned_job(store,title,body,url='',brief=None):
    # The operator supplies original text; none of its instructions are executed here.
    article={'id':'owned_'+digest({'title':title,'body':body,'url':url})[:24], 'title':title,'url':url,'summary':'사용자가 등록한 원문 · 사실 검수 전','evidence':[],'published_at':None,'operator_source_text':body,'preserve_original':True,'source_kind':'owner_supplied','evidence_source_kind':'operator_supplied_text_pending_extraction'}
    job=store.create_job(article,brief)
    if job.get('source_hash') is None:
        store.update_job(job['id'],selections={'blog':True,'video':True,'cards':True,'pdf':False})
        job=store.register_source_input(job['id'],body,None,preserve_original=True)
    return job
