"""Official education notices, publication dates only; never infer exam schedules."""
import hashlib
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from html.parser import HTMLParser

class NoticeTable(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.in_link=False
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row={"text":"", "onclick":"", "title":"", "linktext":""}
        if tag == "a" and self.row is not None:
            self.in_link=True
            self.row["onclick"]=dict(attrs).get("onclick", "")
            self.row["title"]=dict(attrs).get("title", "")
    def handle_data(self,data):
        if self.row is not None:
            self.row["text"] += " " + data
            if self.in_link: self.row["linktext"] += data
    def handle_endtag(self,tag):
        if tag == "a": self.in_link=False
        if tag == "tr" and self.row is not None: self.rows.append(self.row); self.row=None
from .source_registry import classify_article
from .store import now


def parse_moe(raw, feed):
    parser=NoticeTable(); parser.feed(raw.decode('utf-8') if isinstance(raw,bytes) else raw); rows=parser.rows
    if not rows:
        raise ValueError('Official notice table missing; source layout may have changed')
    result = []
    for row in rows:
        link = row if row['onclick'] else None
        dates = re.findall(r'\b20\d{2}-\d{2}-\d{2}\b', row['text'])
        match = re.search(r"goView\('([0-9]+)',\s*'([0-9]+)'", link['onclick']) if link else None
        if not link or not match or not dates:
            continue
        title = link['title'] or re.sub(r'\s+', ' ', row['linktext']).strip()
        if not any(word in title for word in ('수능', '대학', '입시', '직업', '자격', '평생교육', '취업', '학습')):
            continue
        url = f'https://www.moe.go.kr/boardCnts/viewRenew.do?boardID={match[1]}&boardSeq={match[2]}&lev=0&searchType=null&statusYN=W&page=1&s=moe&m=020402&opType=N'
        published = datetime.strptime(dates[0], '%Y-%m-%d').replace(tzinfo=ZoneInfo('Asia/Seoul')).isoformat()
        result.append(classify_article({'id': hashlib.sha256(url.encode()).hexdigest()[:24], 'title': title, 'url': url, 'feed_id': feed['id'], 'feed_name': feed['name'], 'published_at': published, 'retrieved_at': now(), 'summary': '', 'date_status': 'valid', 'segment': 'exam', 'language': 'ko', 'topics': ['수험생', '교육정책'], 'source_kind': 'official_notice', 'date_note': '공지 게시일이며 시험일이 아닙니다'}))
    return result
