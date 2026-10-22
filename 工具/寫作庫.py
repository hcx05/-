"""寫作工具共用函式庫:解析章節大綱、事件、帳本、稱謂表等,供 寫作包/建索引/正文檢查/帳本合併/落稿 使用。
只用標準庫。不要直接執行;由其他腳本 import。"""
import glob
import hashlib
import os
import re
import sys

sys.dont_write_bytecode = True

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

VOLS = ['序卷', '第一部', '第二部', '第三部']
VOL_CODE = {'序卷': 'PRO', '第一部': 'P1', '第二部': 'P2', '第三部': 'P3'}
VOL_SHORT = {'序': '序卷', '一': '第一部', '二': '第二部', '三': '第三部'}
SHORT_OF = {v: k for k, v in VOL_SHORT.items()}
SNAPSHOT_OF = {v: f'狀態/{v}結束' for v in VOLS}


def p(*parts):
    """專案內路徑(相對根目錄)轉絕對路徑。"""
    return os.path.join(ROOT, *parts)


def rel(path):
    return os.path.relpath(path, ROOT)


RECORD = None  # 設成 dict 時,read() 會把讀過的檔(相對路徑 → 內容)記進去;寫作包用它算輸入雜湊


def read(path):
    if not os.path.isabs(path):
        path = p(path)
    with open(path, encoding='utf8') as f:
        text = f.read()
    if RECORD is not None:
        RECORD[rel(path)] = text
    return text


def exists(path):
    return os.path.exists(p(path) if not os.path.isabs(path) else path)


def sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()[:12]


def han_count(text):
    return len(re.findall(r'[一-鿿]', text))


# ---------- 章序 ----------

def vol_rank(vol):
    return VOLS.index(vol)


def chap_key(vol, n):
    return (vol_rank(vol), int(n))


def parse_chap_token(tok):
    """'序1' '一12' → (卷, 章);'*' 或 '末' → None。"""
    tok = tok.strip()
    m = re.fullmatch(r'([序一二三])(\d+)', tok)
    if not m:
        return None
    return VOL_SHORT[m.group(1)], int(m.group(2))


def chap_label(vol, n):
    return f'{SHORT_OF[vol]}{n}'


# ---------- Markdown 表格 ----------

def md_tables(text):
    """回傳 [(標題, [欄名], [[儲存格]...])]。標題為表格前最近的 #~#### 標題。"""
    out = []
    heading = ''
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'#{1,6}\s+(.*)', ln)
        if m:
            heading = m.group(1).strip()
        if ln.lstrip().startswith('|') and i + 1 < len(lines) and re.match(r'\s*\|[\s\-:|]+\|\s*$', lines[i + 1]):
            cols = split_row(ln)
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith('|'):
                rows.append(split_row(lines[j]))
                j += 1
            out.append((heading, cols, rows))
            i = j
            continue
        i += 1
    return out


def split_row(ln):
    s = ln.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|'):
        s = s[:-1]
    return [c.strip() for c in s.split('|')]


def strip_links(s):
    return re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)


# ---------- 章節大綱 ----------

def outline_paths(vol):
    return sorted(glob.glob(p('故事線', vol, '章節', '[0-9][0-9]_第*章_*.md')))


def parse_outline(path):
    text = read(path)
    m = re.match(r'# 第 (\d+) 章 · (.+)', text)
    n, title = int(m.group(1)), m.group(2).strip()
    vol = os.path.normpath(path).split(os.sep)[-3]
    fields = {}
    for fm in re.finditer(r'^- \*\*(.+?)\*\*:(.*)$', text, re.M):
        fields.setdefault(fm.group(1), fm.group(2).strip())
    sections = {}
    for sec in re.split(r'\n(?=## )', text)[1:]:
        head, _, body = sec.partition('\n')
        sections[head[3:].strip()] = body.strip()
    points = []
    body = sections.get('情節要點', '')
    cur = None
    for ln in body.split('\n'):
        mm = re.match(r'(\d+)\.\s+(.*)', ln)
        if mm:
            cur = [int(mm.group(1)), mm.group(2)]
            points.append(cur)
        elif cur is not None and ln.strip():
            cur[1] += '\n' + ln
    ids = lambda key: re.findall(r'[A-Z0-9]+-\d+', fields.get(key, ''))
    return {
        'vol': vol, 'n': n, 'title': title, 'path': rel(path), 'text': text,
        'fields': fields, 'sections': sections, 'points': points,
        'events': ids('對應事件'), 'mentioned': ids('提及事件'),
        'pov': fields.get('視角', ''), 'time': fields.get('時間', ''),
        'budget': fields.get('預計字數', ''),
        'places': re.findall(r'\[([^\]]+)\]\([^)]*場景設定[^)]*\)', fields.get('場景', '')),
        'cast': re.findall(r'\[([^\]]+)\]\([^)]*(?:角色|勢力)[^)]*\)', fields.get('出場角色', '')),
    }


def get_outline(vol, n):
    for pth in outline_paths(vol):
        if os.path.basename(pth).startswith(f'{n:02d}_'):
            return parse_outline(pth)
    return None


def all_outlines(vol=None):
    out = []
    for v in ([vol] if vol else VOLS):
        for pth in outline_paths(v):
            out.append(parse_outline(pth))
    return out


# ---------- 事件 ----------

def parse_events(vol):
    pth = p('故事線', vol, '事件描述.md')
    if not os.path.exists(pth):
        return {}
    out = {}
    for sec in re.split(r'\n(?=### )', read(pth)):
        m = re.match(r'### (\S+) (.*)', sec)
        if not m:
            continue
        ev = {'id': m.group(1), 'name': m.group(2).strip(), 'vol': vol}
        for fm in re.finditer(r'^- \*\*(.+?)\*\*:(.*)$', sec, re.M):
            ev[fm.group(1)] = fm.group(2).strip()
        ev['serial'] = int(re.sub(r'\D', '', ev.get('序號', '0')) or 0)
        ev['cast'] = re.findall(r'\[([^\]]+)\]\(', ev.get('出場角色', ''))
        out[ev['id']] = ev
    return out


_EV_CACHE = {}


def all_events():
    if not _EV_CACHE:
        for v in VOLS:
            _EV_CACHE.update(parse_events(v))
    return _EV_CACHE


def chapter_cutoff(outline):
    """本章最後一個演出事件在其卷時間線中的序號(用於過濾「未來」資料)。"""
    evs = all_events()
    serials = [evs[e]['serial'] for e in outline['events'] if e in evs]
    return max(serials) if serials else 0


def event_serial(eid):
    ev = all_events().get(eid)
    return ev['serial'] if ev else None


# ---------- 角色 ----------

def parse_id_map():
    """ID對照:{名稱: (ID, 路徑)};分角色/勢力/場景。"""
    text = read('設計規範/ID對照.md')
    res = {'角色': {}, '勢力': {}, '場景': {}}
    for head, cols, rows in md_tables(text):
        key = '角色' if '角色' in head else '勢力' if '勢力' in head else '場景' if '場景' in head else None
        if not key or len(cols) < 3:
            continue
        for r in rows:
            if len(r) >= 3:
                res[key][r[1]] = (r[0], r[2].strip('`'))
    return res


# 人名別名:資料在 正文/技法/稱謂表.md 第三節(「正名 | 別名」),載入後填入下面這個 dict。
# 新增別名請改該表,不要改程式。(敘述用名仍以稱謂表第一節為準;這裡只供辨識「這是誰」。)
NAME_ALIASES = {}


def load_aliases():
    NAME_ALIASES.clear()
    pth = '正文/技法/稱謂表.md'
    if not exists(pth):
        return
    for head, cols, trs in md_tables(read(pth)):
        if cols[:2] == ['正名', '別名']:
            for r in trs:
                al = [x.strip() for x in re.split(r'[、,，]', r[1]) if x.strip() and x.strip() not in ('—', '-')]
                NAME_ALIASES[r[0]] = al


def char_dir(name):
    idm = parse_id_map()['角色']
    if name in idm:
        return idm[name][1]
    return None


# ---------- 帳本 ----------

LEDGER_SECTIONS = ['摘要', '時間地點', '章末人物狀態', '物件', '數字事實', '稱呼', '新增專名',
                   '新增事實', '伏筆動作', '要點對照', '與大綱出入']
LEDGER_TABLE_COLS = {
    '時間地點': ['項目', '內容'],
    '章末人物狀態': ['角色', '位置', '傷勢', '持物', '狀態', '本章新知', '本章新疑'],
    '物件': ['ID', '名稱', '持有者', '狀態'],
    '數字事實': ['項目', '值', '備註'],
    '稱呼': ['誰', '稱呼誰', '用語', '備註'],
    '新增專名': ['類型', '名稱', '登記', '備註'],
    '新增事實': ['ID', '事實', '回補'],
    '伏筆動作': ['THR', '動作', '備註'],
    '要點對照': ['要點', '場景', '備註'],
    '與大綱出入': ['條目', '處置'],
}


def ledger_path(vol, n):
    return p('正文', '帳本', vol, f'第{n:02d}章.帳本.md')


def parse_ledger(path):
    """回傳 dict:head(標頭資訊)、sections[名稱]=原文、tables[名稱]=[dict列]、errors[]。"""
    text = read(path)
    res = {'path': rel(path), 'text': text, 'sections': {}, 'tables': {}, 'errors': []}
    m = re.match(r'# 帳本 · (\S+) · 第 (\d+) 章(?: (.*))?', text)
    if not m:
        res['errors'].append('標題格式應為「# 帳本 · {卷} · 第 N 章 標題」')
        return res
    res['vol'], res['n'], res['title'] = m.group(1), int(m.group(2)), (m.group(3) or '').strip()
    for sec in re.split(r'\n(?=## )', text)[1:]:
        head, _, body = sec.partition('\n')
        name = head[3:].strip()
        res['sections'][name] = body.strip()
    for name in LEDGER_SECTIONS:
        if name not in res['sections']:
            res['errors'].append(f'缺少「## {name}」')
    for name, cols in LEDGER_TABLE_COLS.items():
        body = res['sections'].get(name)
        if body is None:
            continue
        tabs = md_tables(body)
        if not tabs:
            if '(無)' in body or '無' == body.strip():
                res['tables'][name] = []
                continue
            res['errors'].append(f'「{name}」沒有表格(無內容請寫「(無)」)')
            continue
        _, hcols, rows = tabs[0]
        if hcols[:len(cols)] != cols:
            res['errors'].append(f'「{name}」欄位應為 {cols},實際 {hcols}')
            continue
        recs = []
        for r in rows:
            r = r + [''] * (len(cols) - len(r))
            recs.append(dict(zip(cols, r)))
        res['tables'][name] = recs
    return res


def ledger_files():
    """依章序排列的 (卷, 章, 路徑)。"""
    out = []
    for v in VOLS:
        for f in glob.glob(p('正文', '帳本', v, '第*章.帳本.md')):
            m = re.search(r'第(\d+)章\.帳本\.md', f)
            out.append((v, int(m.group(1)), f))
    out.sort(key=lambda t: chap_key(t[0], t[1]))
    return out


def ledgers_before(vol, n):
    """嚴格早於 (vol, n) 的所有帳本(已解析)。"""
    k = chap_key(vol, n)
    return [parse_ledger(f) for v, c, f in ledger_files() if chap_key(v, c) < k]


def fold_ledgers(ledgers):
    """折疊帳本 → 累積狀態 dict。後章覆蓋前章(人物、物件、稱呼);專名、事實、數字累積。"""
    st = {'chars': {}, 'items': {}, 'calls': {}, 'numbers': [], 'names': [], 'facts': [], 'last': None}
    for lg in ledgers:
        if 'vol' not in lg:
            continue
        tag = chap_label(lg['vol'], lg['n'])
        st['last'] = (lg['vol'], lg['n'])
        for r in lg['tables'].get('章末人物狀態', []):
            r = dict(r)
            r['章'] = tag
            st['chars'][r['角色']] = r
        for r in lg['tables'].get('物件', []):
            r = dict(r)
            r['章'] = tag
            st['items'][r['ID']] = r
        for r in lg['tables'].get('稱呼', []):
            r = dict(r)
            r['章'] = tag
            st['calls'][(r['誰'], r['稱呼誰'])] = r
        for r in lg['tables'].get('數字事實', []):
            st['numbers'].append(dict(r, 章=tag))
        for r in lg['tables'].get('新增專名', []):
            st['names'].append(dict(r, 章=tag))
        for r in lg['tables'].get('新增事實', []):
            st['facts'].append(dict(r, 章=tag))
        t = {r['項目']: r['內容'] for r in lg['tables'].get('時間地點', [])}
        st['time_end'] = t.get('迄', '')
        st['time_end_tag'] = tag
    return st


# ---------- 稱謂表 ----------

def parse_naming():
    """稱謂表 → [{角色, 起, 迄, 可用, 禁用}];起迄為 (卷, 章) 或 None(迄 '*' = 不設限)。"""
    pth = '正文/技法/稱謂表.md'
    if not exists(pth):
        return []
    rows = []
    for head, cols, trs in md_tables(read(pth)):
        if cols[:5] != ['角色', '起', '迄', '敘述可用', '敘述禁用']:
            continue
        for r in trs:
            r = r + [''] * (6 - len(r))
            start = parse_chap_token(r[1])
            end = None if r[2].strip() in ('*', '末') else parse_chap_token(r[2])
            split = lambda s: [x.strip() for x in re.split(r'[、,，]', s) if x.strip() and x.strip() not in ('—', '-')]
            rows.append({'角色': r[0], 'start': start, 'end': end,
                         '可用': split(r[3]), '禁用': split(r[4]), '待決': split(r[5])})
    return rows


def naming_for(vol, n):
    k = chap_key(vol, n)
    out = []
    for r in parse_naming():
        if r['start'] and chap_key(*r['start']) > k:
            continue
        if r['end'] and chap_key(*r['end']) < k:
            continue
        out.append(r)
    return out


def parse_reveals():
    """稱謂表第二張表 → [{詞, 最早章(卷,章), 依據, 強度}]"""
    pth = '正文/技法/稱謂表.md'
    if not exists(pth):
        return []
    out = []
    for head, cols, trs in md_tables(read(pth)):
        if cols[:2] != ['詞', '最早章']:
            continue
        for r in trs:
            r = r + [''] * (4 - len(r))
            out.append({'詞': r[0], 'first': parse_chap_token(r[1]), '依據': r[2], '強度': r[3] or '硬'})
    return out


def reveals_blocked(vol, n):
    """本章之前尚不得出現的詞。"""
    k = chap_key(vol, n)
    return [r for r in parse_reveals() if r['first'] and chap_key(*r['first']) > k]


# ---------- 術語、事實 ----------

def parse_terms():
    res = []
    for head, cols, rows in md_tables(read('設計規範/術語表.md')):
        if len(cols) >= 3 and cols[0] == '標準寫法':
            for r in rows:
                if len(r) >= 3:
                    bad = [x.strip() for x in re.split(r'[、,，]', r[2]) if x.strip()]
                    res.append({'標準': r[0], '說明': r[1], '避免': bad})
    return res


def parse_facts():
    res = []
    for head, cols, rows in md_tables(read('設計規範/事實登錄.md')):
        if cols[:2] == ['ID', '事實']:
            for r in rows:
                if len(r) >= 2:
                    res.append({'ID': r[0], '事實': r[1], '出處': r[2] if len(r) > 2 else '', '類': head})
    return res


def parse_decisions():
    res = []
    for head, cols, rows in md_tables(read('設計規範/設計決定記錄.md')):
        if cols[:2] == ['ID', '決定']:
            for r in rows:
                if len(r) >= 2:
                    res.append({'ID': r[0], '決定': r[1], '理由': r[2] if len(r) > 2 else ''})
    return res


# ---------- 正文 ----------

def prose_files(vol=None):
    out = []
    for v in ([vol] if vol else VOLS):
        for f in glob.glob(p('正文', v, '第*章_*.md')):
            m = re.search(r'第(\d+)章_(.+)\.md', os.path.basename(f))
            out.append((v, int(m.group(1)), m.group(2), f))
    out.sort(key=lambda t: chap_key(t[0], t[1]))
    return out


def prose_path(vol, n):
    for v, c, t, f in prose_files(vol):
        if c == n:
            return f
    return None


def prose_body(text):
    """去掉標題與引言行,回傳正文本體。"""
    lines = text.split('\n')
    i = 0
    while i < len(lines) and (lines[i].startswith('#') or lines[i].startswith('>') or not lines[i].strip()):
        i += 1
    return '\n'.join(lines[i:])


def prev_chapter(vol, n):
    """上一章 (卷, 章);跨卷時取前一卷最後一個有正文的章。"""
    files = [(v, c) for v, c, t, f in prose_files()]
    k = chap_key(vol, n)
    prior = [x for x in files if chap_key(*x) < k]
    return prior[-1] if prior else None


def truncate(s, limit, note='…(略,用 工具/查詢.py 取全文)'):
    if len(s) <= limit:
        return s
    return s[:max(0, limit - len(note))].rstrip() + note


# ---------- 時間線年齡、首現、讀者知識 ----------

def timeline_ages(vol):
    """時間線 → {事件ID: ((男主最小,最大), (女主最小,最大))};「9–12」這類區間取兩端,「—」為 None。"""
    pth = f'故事線/{vol}/時間線.md'
    if not exists(pth):
        return {}

    def rng(cell):
        nums = [int(x) for x in re.findall(r'\d+', cell)]
        return (min(nums), max(nums)) if nums else None

    out = {}
    for head, cols, rows in md_tables(read(pth)):
        if '事件 ID' in cols and '男主' in cols:
            i, a, b = cols.index('事件 ID'), cols.index('男主'), cols.index('女主')
            for r in rows:
                if len(r) > max(i, a, b):
                    out[r[i]] = (rng(r[a]), rng(r[b]))
    return out


_FIRST_CACHE = {}


def first_appearances():
    """依章節大綱算出每個登記名稱(角色、勢力)的計畫首現:
    {名稱: {'cast': (卷,章)或None, 'mention': (卷,章)或None}}。cast = 列入「出場角色」;mention = 大綱任何位置提到。"""
    if _FIRST_CACHE:
        return _FIRST_CACHE
    idm = parse_id_map()
    names = [n for n in list(idm['角色']) + list(idm['勢力']) if n not in ('男主', '女主') and len(n) >= 2]
    for n in names:
        _FIRST_CACHE[n] = {'cast': None, 'mention': None}
    for o in all_outlines():
        key = (o['vol'], o['n'])
        for n in names:
            rec = _FIRST_CACHE[n]
            if rec['cast'] is None and n in o['cast']:
                rec['cast'] = key
            if rec['mention'] is None and n in o['text']:
                rec['mention'] = key
    return _FIRST_CACHE


def reader_knowledge(vol, n, last=3):
    """截至 (vol, n) 之前最近 last 章,章節大綱「資訊揭露」所安排讀者得知的內容(計畫值,以帳本實況為準)。"""
    k = chap_key(vol, n)
    outs = [o for o in all_outlines() if chap_key(o['vol'], o['n']) < k]
    return [(o['vol'], o['n'], o['title'], o['sections'].get('資訊揭露', '').strip()) for o in outs[-last:]]


def reset_caches():
    _EV_CACHE.clear()
    _FIRST_CACHE.clear()


def open_questions():
    """待決單 → [{id, 標題, 狀態, 暫行, 影響}]。"""
    d = p('正文', '待決')
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        m = re.fullmatch(r'(Q-\d+)\.md', f)
        if not m:
            continue
        t = read(os.path.join(d, f))
        st = re.search(r'\*\*狀態\*\*:(.*)', t)
        zh = re.search(r'\*\*暫行做法\*\*:(.*)', t)
        sc = re.search(r'\*\*影響範圍\*\*:(.*)', t)
        out.append({'id': m.group(1), '標題': t.split('\n')[0][2:].strip(), '狀態': st.group(1).strip() if st else '',
                    '暫行': zh.group(1).strip() if zh else '', '影響': sc.group(1).strip() if sc else ''})
    return out


load_aliases()
