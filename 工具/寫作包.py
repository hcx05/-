#!/usr/bin/env python3
"""寫作包:為指定的章產生一份自足的寫作輸入檔,模型寫這一章只需讀它(外加受控查詢)。

用法:
    python3 工具/寫作包.py 第一部 2                 # 寫入 正文/包/第一部/第02章.包.md
    python3 工具/寫作包.py 第一部 2 --精簡          # 精簡版,給上下文較小的模型
    python3 工具/寫作包.py 第一部 2 --stdout        # 印到標準輸出,不寫檔

原則:同一份倉庫狀態、同一組參數,輸出完全相同(包頭的輸入雜湊可驗證)。
資料取「截至本章」:不讀未來卷、不讀本章之後的事件、不用卷末快照代替章前狀態。
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

# 各節字數預算(完整, 精簡)
BUDGET = {
    'A': (2500, 1500), 'B': (6000, 4200), 'C': (3500, 2200), 'D': (4500, 2600),
    'E': (2500, 1200), 'F': (2600, 1600), 'G': (3900, 2200), 'H': (2200, 900), 'I': (1500, 900),
}

USED = {}  # 路徑 → 內容,用來算輸入雜湊


def rd(path):
    """讀檔並記錄為輸入;不存在回傳 None。"""
    if not L.exists(path):
        return None
    full = path if os.path.isabs(path) else L.p(path)
    rp = L.rel(full)
    if rp not in USED:
        USED[rp] = L.read(full)
    return USED[rp]


def clip(s, n):
    return L.truncate(s, n)


def flat(s):
    """內嵌內容的 Markdown 標題改為粗體,避免和包本身的節標題混淆。"""
    return re.sub(r'(?m)^#{1,6}\s+(.*)$', r'**\1**', s)


def section_blocks(text, level='###'):
    return re.split(r'\n(?=' + level + r' )', text)


EVID = re.compile(r'(?:PRO|P[123])-\d{3}')


def filtered_memory(path, vol, cutoff, current):
    """讀記憶檔;當前卷只保留事件序號 ≤ cutoff 的段落,前卷全部保留。回傳 [段落文字]。"""
    text = rd(path)
    if not text:
        return []
    out = []
    for blk in section_blocks(text):
        if not blk.startswith('### '):
            continue
        ids = EVID.findall(blk.split('\n', 1)[0])
        if not ids:
            continue
        if current:
            sers = [L.event_serial(i) for i in ids]
            if any(s is None or s > cutoff for s in sers):
                continue
        out.append(blk.strip())
    return out


def role_path(name):
    d = L.char_dir(name)
    return d.rstrip('/') if d else None


# ---------------------------------------------------------------- 各節

def sec_A(o, keys, compact):
    parts = []
    t = rd('手冊/鐵律卡.md')
    if t:
        parts.append(re.sub(r'^# .*\n+', '', t).strip())
    facts = L.parse_facts()
    hit = []
    for f in facts:
        score = sum(1 for k in keys if k and k in f['事實'])
        if score:
            hit.append((score, f))
    hit.sort(key=lambda t: (-t[0], t[1]['ID']))
    lim = 6 if compact else 12
    if hit:
        parts.append('**與本章相關的硬規則(事實登錄)**')
        for _, f in hit[:lim]:
            parts.append(f"- {f['ID']}:{clip(f['事實'], 110)}")
    orgs = set(L.parse_id_map()['勢力'])
    dkeys = [k for k in keys if k not in orgs] + [o['vol'] + ' ' + '第 ' + str(o['n']) + ' 章', o['vol'] + '第 ' + str(o['n']) + ' 章']
    decs = [d for d in L.parse_decisions() if any(k and k in d['決定'] for k in dkeys)]
    if decs:
        parts.append('**相關設計決定**')
        for d in decs[: (3 if compact else 6)]:
            parts.append(f"- {d['ID']}:{clip(d['決定'], 120)}")
    return '\n\n'.join(parts)


def sec_B(o, compact):
    parts = []
    patches = [(h, b_) for h, b_ in o['sections'].items() if re.search(r'增補|改版|對齊|DEC-\d+', h)]
    if patches:
        parts.append('**大綱補丁(下列段落是後來才加的修正;與大綱本文衝突時,以補丁為準)**')
        for h, b_ in patches:
            parts.append(f'- 〈{h}〉:' + re.sub(r'\s*\n\s*', ' ', b_.strip()))
        parts.append('')
    parts += ['**章節大綱(正本:`' + o['path'] + '`)**', '', o['text'].strip(), '']
    evs = L.all_events()
    parts.append('**對應事件(演出)**')
    for e in o['events']:
        ev = evs.get(e)
        if ev:
            parts.append(f"- {e} {ev['name']}({ev.get('時間', '')}):{clip(ev.get('描述', ''), 160)}")
    if o['mentioned']:
        parts.append('**提及事件(口述或回想)**')
        for e in o['mentioned']:
            ev = evs.get(e)
            if ev:
                parts.append(f"- {e} {ev['name']}:{clip(ev.get('描述', ''), 90)}")
    parts.append('')
    parts.append('**字數**:大綱「預計字數」按含標點估算;已定稿章的實寫漢字數約為其 60% 至 76%(DEC-077 曾以 80% 為擴寫目標;口徑見待決單 Q-002)。字數是參考,不是驗收條件。')
    return '\n'.join(parts)


def snapshot_rows(vol):
    """前一卷卷末快照的角色狀態 → {角色: row dict}。序卷無前卷快照。"""
    idx = L.vol_rank(vol)
    if idx == 0:
        return {}, None
    prev = L.VOLS[idx - 1]
    path = f'狀態/{prev}結束/角色狀態.md'
    text = rd(path)
    res = {}
    if text:
        for head, cols, rows in L.md_tables(text):
            if cols and cols[0] == '角色':
                for r in rows:
                    res[r[0]] = dict(zip(cols, r))
    return res, prev


def sec_C(o, compact):
    prior = L.ledgers_before(o['vol'], o['n'])
    st = L.fold_ledgers(prior)
    cast = [c for c in o['cast'] if c in st['chars'] or True]
    snap, snap_vol = snapshot_rows(o['vol'])
    parts = []
    if not prior:
        parts.append('(這是目前最早的一章,沒有前章帳本。起點狀態依章節大綱與角色設定。)')
    else:
        parts.append(f"**承接**:前章為 {L.chap_label(*st['last'])},其章末時間地點:{st.get('time_end', '')}")
        parts.append('')
        parts.append('**章末人物狀態(取最近一次記錄;下列人物與本章出場者有關)**')
        shown = 0
        for name in o['cast']:
            r = st['chars'].get(name)
            if r:
                parts.append(f"- {name}(據{r['章']}):位置:{r['位置']};傷勢:{r['傷勢']};持物:{r['持物']};狀態:{r['狀態']};新知:{r['本章新知']};新疑:{r['本章新疑']}")
                shown += 1
        others = [n for n in st['chars'] if n not in o['cast']]
        if others:
            parts.append(f"- (其他有記錄但本章不在場:{'、'.join(others)})")
    # 沒有帳本記錄的出場者:用前卷快照
    if snap:
        missing = [n for n in o['cast'] if n not in st['chars'] and n in snap]
        if missing:
            parts.append('')
            parts.append(f'**起始快照(取自{snap_vol}結束;尚無帳本記錄的出場者)**')
            for n in missing:
                r = snap[n]
                parts.append(f"- {n}:位置:{r.get('位置', '')};身份:{r.get('身份', '')};年齡:{r.get('年齡', '')};當前個性:{clip(r.get('當前個性', ''), 70)};已知:{clip(r.get('已知的關鍵事項', ''), 120)};未知或誤信:{clip(r.get('未知或誤信', ''), 100)}")
    items = [r for r in st['items'].values() if re.split(r'[(（]', r['持有者'])[0].strip() in o['cast']]
    if items:
        parts.append('')
        parts.append('**物件(持有者在本章出場者之列)**')
        for r in items:
            parts.append(f"- {r['ID']} {r['名稱']}:持有者 {r['持有者']};{r['狀態']}(據{r['章']})")
    calls = [r for r in st['calls'].values() if r['稱呼誰'] in o['cast']]
    if calls:
        parts.append('')
        parts.append('**既有稱呼(別人如何稱呼本章出場者)**')
        for r in calls:
            note = f"({r['備註']})" if r['備註'] else ''
            parts.append(f"- {r['誰']}→{r['稱呼誰']}:{r['用語']}{note}")
    last = recent_chapters(o, 1)
    recent = [r for r in st['numbers'] if last and r['章'] == L.chap_label(*last[0])]
    if recent:
        parts.append('')
        parts.append('**前章數字事實**')
        for r in recent:
            note = f"({r['備註']})" if r['備註'] else ''
            parts.append(f"- {r['項目']}={r['值']}{note}")
    return '\n'.join(parts)


def recent_chapters(o, k=2):
    files = [(v, c) for v, c, f in L.ledger_files() if L.chap_key(v, c) < L.chap_key(o['vol'], o['n'])]
    return files[-k:]


def voice_card(name):
    t = rd('正文/技法/聲口卡.md')
    if not t:
        return ''
    for blk in re.split(r'\n(?=## )', t):
        head = blk.split('\n', 1)[0]
        if name in head or (name == '男主' and '懷川' in head) or (name == '呼延阿古' and '阿古' in head) or (name == '秦七' and '七叔' in head):
            lines = [l for l in blk.split('\n')[1:] if l.startswith('- ')]
            return '\n'.join(lines)
    return ''


def char_profile(name, o, compact):
    path = role_path(name)
    if not path:
        return None
    vol, cutoff = o['vol'], L.chapter_cutoff(o)
    out = []
    vc = voice_card(name)
    if vc:
        out.append('聲口:\n' + clip(vc, 520 if not compact else 300))
    # 設定
    setting = None
    if name in ('男主', '女主'):
        setting = rd(f'{path}/個性/初始個性.md')
        if setting:
            lines = []
            sec = ''
            for ln in setting.split('\n'):
                if ln.startswith('## '):
                    sec = ln[3:].strip()
                    continue
                if sec in ('外表', '核心個性', '行為習慣') and ln.startswith('- '):
                    lines.append(ln)
                elif sec == '核心個性' and ln.startswith('|') and not re.match(r'\|[\s\-|]+\|$', ln) and '性格' not in ln:
                    cells = L.split_row(ln)
                    if len(cells) >= 2:
                        lines.append(f'- {cells[0]}:{cells[1]}')
            out.append('設定:\n' + clip('\n'.join(lines), 520 if not compact else 300))
            setting = None
    else:
        setting = rd(f'{path}/設定/{vol}.md')
        if setting is None and L.vol_rank(vol) > 0:
            setting = rd(f'{path}/設定/{L.VOLS[L.vol_rank(vol)-1]}.md')
    if setting:
        keep = [l for l in setting.split('\n') if re.match(r'- \*\*(性別|初始年齡|身份|外表|初始個性|戰力|武學|所屬)', l)]
        body = '\n'.join(keep) if keep else re.sub(r'^#.*\n', '', setting)
        out.append('設定:\n' + clip(body, 480 if not compact else 280))
    # 記憶:前卷全部、當前卷依事件過濾;取最近的段落
    mems = []
    for v in L.VOLS[: L.vol_rank(vol) + 1]:
        mp = f'{path}/成長/記憶/{v}.md'
        mems += filtered_memory(mp, v, cutoff, current=(v == vol))
    if mems:
        picked, size = [], 0
        lim = 700 if not compact else 380
        for blk in reversed(mems):
            head, _, rest = blk.partition('\n')
            b = '**' + head.lstrip('# ').strip() + '** ' + re.sub(r'\n+', ' ', rest).replace('- **', '**')
            if size + len(b) > lim and picked:
                break
            picked.append(clip(b, lim))
            size += len(b)
        out.append('此刻所知(記憶檔,截至本章事件):\n' + '\n'.join('- ' + b for b in reversed(picked)))
    return '\n\n'.join(out) if out else ''


def sec_D(o, compact):
    parts = []
    seen = []
    for name in o['cast']:
        if name in seen:
            continue
        seen.append(name)
        idm = L.parse_id_map()['角色']
        if name not in idm:
            continue
        prof = char_profile(name, o, compact)
        if prof is None:
            continue
        parts.append(f'### {name}({idm[name][0]})\n{prof if prof else "(無檔案內容;用 工具/查詢.py 取)"}')
    orgs = [c for c in o['cast'] if c in L.parse_id_map()['勢力']]
    if orgs:
        parts.append('出場勢力:' + '、'.join(orgs) + '(細節用 `工具/查詢.py 名稱`)')
    return '\n\n'.join(parts)


def sec_E(o, compact):
    parts = []
    idm = L.parse_id_map()['場景']
    for place in o['places']:
        if place not in idm:
            parts.append(f'- {place}:尚無建模(待建)')
            continue
        d = idm[place][1].rstrip('/')
        t = rd(f'{d}/建模描述.md')
        if not t:
            continue
        keep = []
        for blk in re.split(r'\n(?=## )', t):
            head = blk.split('\n', 1)[0]
            if head.startswith('## 整體描述') or head.startswith('## 空間結構'):
                keep.append(blk.strip())
        added = [l for l in t.split('\n') if '新增' in l and l.startswith('- ')]
        txt = '\n'.join(keep)
        if added:
            txt += '\n' + '\n'.join(added)
        parts.append(f'### {place}\n' + flat(clip(txt, 900 if not compact else 450)))
    # 招式
    mp = f'武學設定/招式/{o["vol"]}招式錄.md'
    t = rd(mp)
    if t:
        rows = []
        for head, cols, trs in L.md_tables(t):
            if cols and cols[0] == '事件 ID':
                for r in trs:
                    if r[0] in o['events']:
                        rows.append('- ' + ' / '.join(r[:6]))
        if rows:
            parts.append('### 本章出場的武學與招式(招式錄)\n' + '\n'.join(rows))
    return '\n\n'.join(parts) if parts else '(本章無場景建模與招式錄條目)'


def thread_rows(o):
    text = rd('狀態/伏筆登記簿.md') or ''
    ids = set(o['events'])
    rows = []
    for head, cols, trs in L.md_tables(text):
        if cols and cols[0] == 'ID':
            for r in trs:
                blob = ' '.join(r[1:5])
                touched = [e for e in ids if e in blob]
                if touched:
                    rows.append((r, touched))
    return rows


def sec_F(o, compact):
    parts = []
    nm = L.naming_for(o['vol'], o['n'])
    if nm:
        parts.append('**敘述稱呼(稱謂表)**')
        for r in nm:
            seg = f"- {r['角色']}:可用「{'、'.join(r['可用']) or '—'}」"
            if r['禁用']:
                seg += f";**禁用**「{'、'.join(r['禁用'])}」"
            if r['待決']:
                seg += f";待決(尚未定,避免使用)「{'、'.join(r['待決'])}」"
            parts.append(seg)
    blocked = L.reveals_blocked(o['vol'], o['n'])
    if blocked:
        parts.append('')
        parts.append('**本章尚不得出現的詞(依稱謂表第二節;何時可出現見括號)**')
        parts.append('、'.join(f"{r['詞']}({L.chap_label(*r['first'])}{'' if r['強度'] == '硬' else ',提示'})" for r in blocked))
    th = thread_rows(o)
    if th:
        parts.append('')
        parts.append('**與本章事件有關的伏筆(伏筆登記簿)**')
        for r, touched in th:
            later = re.match(r'(序卷|第[一二三]部)', r[3].strip())
            fut = f"預計於{later.group(1)}回收" if later else '回收時點見伏筆登記簿'
            parts.append(f"- {r[0]} {clip(r[1], 50)}:設置 {clip(r[2], 30)};{fut}(細節不在本章揭露);涉及 {'、'.join(touched)}")
    sec = rd('狀態/秘密知情矩陣.md') or ''
    secs = []
    for head, cols, trs in L.md_tables(sec):
        if cols and cols[0] == 'ID' and len(cols) > 3:
            for r in trs:
                secs.append(f'{r[0]} {clip(r[1], 28)}')
            break
    if secs:
        parts.append('')
        parts.append('**全書秘密清單(作者知,角色與讀者不一定知)**:除非本章大綱「資訊揭露」明列可知,一律不揭露、不暗示答案:' + ';'.join(secs[: (8 if compact else 20)]))
    qs = []
    for q in sorted(os.listdir(L.p('正文', '待決'))):
        if re.match(r'Q-\d+\.md', q):
            t = rd(f'正文/待決/{q}')
            if '狀態**:待決' in t:
                title = t.split('\n')[0][2:]
                m = re.search(r'\*\*暫行做法\*\*:(.*)', t)
                qs.append(f"- {title}。暫行:{clip(m.group(1) if m else '', 130)}")
    if qs:
        parts.append('')
        parts.append('**未決事項(照暫行做法寫,不要自行裁決)**')
        parts += qs
    return '\n'.join(parts)


def tail_of_prose(vol, n, k):
    pth = L.prose_path(vol, n)
    if not pth:
        return ''
    body = L.prose_body(L.read(pth))
    USED[L.rel(pth)] = L.read(pth)
    paras = [p_ for p_ in body.split('\n') if p_.strip()]
    out, size = [], 0
    for p_ in reversed(paras):
        if size + len(p_) > k and out:
            break
        out.append(p_)
        size += len(p_)
    return '\n\n'.join(reversed(out))


def sec_G(o, compact):
    prev = L.prev_chapter(o['vol'], o['n'])
    if not prev:
        return '(沒有前文。)'
    parts = []
    sums = []
    for v, c in recent_chapters(o, 3):
        lg = L.parse_ledger(L.ledger_path(v, c))
        s = lg['sections'].get('摘要', '') if 'vol' in lg else ''
        if s:
            sums.append(f'- {L.chap_label(v, c)} {lg.get("title", "")}:' + ' '.join(l.lstrip('- ').strip() for l in s.split('\n') if l.strip()))
    if sums:
        parts.append('**近章摘要(帳本)**')
        parts += [clip(s_, 360) for s_ in sums]
    rk = L.reader_knowledge(o['vol'], o['n'], 3)
    if rk:
        parts.append('')
        parts.append('**讀者此刻應已得知的事(依前三章大綱「資訊揭露」的計畫值;實況以上列摘要與帳本為準)**')
        for v, c, t, txt in rk:
            if txt:
                parts.append(f'- {L.chap_label(v, c)} {t}:' + clip(re.sub(r'\s*\n\s*', ' ', txt), 240))
    pv, pc = prev
    parts.append('')
    parts.append(f'**前章({L.chap_label(pv, pc)})結尾原文**(銜接用,不得照抄)')
    parts.append(tail_of_prose(pv, pc, 1500 if not compact else 800))
    return '\n'.join(parts)


KIND_KEYS = {
    '打戲': ['戰', '打', '交手', '追殺', '伏擊', '突圍', '搜查', '對峙', '刀', '劍', '槍'],
    '情感': ['死', '葬', '哭', '訣別', '遺言', '重逢', '愧疚', '告別', '離別', '傷'],
    '群像': ['幽默', '吵', '賭', '客棧', '驛', '酒', '市', '群像'],
    '內心': ['回想', '改觀', '心境', '夜', '療傷', '猶豫', '信任'],
}


def sec_H(o, compact):
    t = rd('正文/技法/風格樣本.md')
    if not t:
        return '(尚無風格樣本)'
    blocks = {}
    for blk in re.split(r'\n(?=## )', t)[1:]:
        head = blk.split('\n', 1)[0][3:]
        blocks[head] = blk.strip()
    text = o['text']
    order = []
    for kind, keys in KIND_KEYS.items():
        score = sum(text.count(k) for k in keys)
        order.append((score, kind))
    order.sort(key=lambda t_: (-t_[0], t_[1]))
    prefix = {'打戲': '打戲', '情感': '情感', '群像': '群像', '內心': '近距離內心'}
    picked = ['日常對話']
    for score, kind in order:
        if score > 0 and len(picked) < (2 if compact else 3):
            picked.append(prefix[kind])

    def source_key(head):
        m = re.search(r'(序卷|第[一二三]部)第 (\d+) 章', head)
        return L.chap_key(m.group(1), m.group(2)) if m else None

    here = L.chap_key(o['vol'], o['n'])
    out = []
    for pre in picked:
        for head, blk in blocks.items():
            if head.startswith(pre):
                sk = source_key(head)
                # 優先用不晚於本章的樣本;全部都晚於本章時才破例(只為語感)
                if sk is None or sk <= here or not any((source_key(h) or (0, 0)) <= here for h in blocks):
                    out.append(flat(blk))
                break
    return clip('\n\n'.join(out), 5000)


def sec_I():
    t = rd('手冊/提示/落稿格式.md')
    return re.sub(r'^# .*\n+', '', t or '(缺 手冊/提示/落稿格式.md)').strip()


# ---------------------------------------------------------------- 組裝

def build(vol, n, compact=False):
    USED.clear()
    o = L.get_outline(vol, n)
    if not o:
        raise SystemExit(f'找不到 {vol} 第 {n} 章的章節大綱')
    keys = [c for c in o['cast'] if c not in ('男主', '女主')] + o['places'] + [o['title']]
    idx = 1 if compact else 0
    secs = [
        ('A', '鐵律與相關硬規則', sec_A(o, keys, compact)),
        ('B', '本章規格', sec_B(o, compact)),
        ('C', '章前狀態', sec_C(o, compact)),
        ('D', '在場人物卡', sec_D(o, compact)),
        ('E', '場景與武學', sec_E(o, compact)),
        ('F', '稱呼、伏筆與禁區', sec_F(o, compact)),
        ('G', '前文接續', sec_G(o, compact)),
        ('H', '風格樣本(只示語感,不得抄句)', sec_H(o, compact)),
        ('I', '交付格式與自檢', sec_I()),
    ]
    body = []
    report = []
    for key, title, text in secs:
        lim = BUDGET[key][idx]
        # B 與 I 是規格本身,不截斷;只在報表標記超出
        if key not in ('B', 'I'):
            text = clip(text, lim)
        report.append((key, title, len(text), lim))
        body.append(f'## {key}. {title}\n\n{text}\n')
    digest = L.sha('\n'.join(f'{k}\n{v}' for k, v in sorted(USED.items())))
    label = '精簡包' if compact else '完整包'
    gaps = [oo for oo in L.all_outlines() if L.chap_key(oo['vol'], oo['n']) < L.chap_key(vol, n)
            and not os.path.exists(L.ledger_path(oo['vol'], oo['n']))]
    warn = ''
    if gaps:
        names = '、'.join(L.chap_label(g['vol'], g['n']) for g in gaps[:5]) + ('…' if len(gaps) > 5 else '')
        warn = f'> ⚠ **順序警告**:本章之前還有 {len(gaps)} 章沒有帳本({names}),章前狀態與前文接續不完整。依序寫完前面的章再寫本章;若只是預覽,資料僅供參考,不可據此定稿。\n'
    head = [
        f"# 寫作包 · {vol} · 第 {n} 章 {o['title']}({label})",
        '',
        f'> 輸入雜湊:{digest}(由 {len(USED)} 個來源檔算出;同一倉庫狀態重跑結果相同)。導出檔,請勿手改;不提交入庫。',
        warn.rstrip('\n') if warn else None,
        '> 用法:這份包是寫本章的**唯一必讀輸入**。需要包外資料時,用 `python3 工具/查詢.py 名稱 --至 ' + f'{vol}{n}' + '`(自動排除未來內容),不要自行翻找未來卷。遇到包內資料互相矛盾或不足以下筆,依[優先序與衝突](../../../手冊/優先序與衝突.md)處理並開待決單,不要自行發明。',
        '',
        '| 節 | 內容 | 字數 | 預算 |',
        '|---|---|---|---|',
    ]
    for key, title, size, lim in report:
        flag = '' if size <= lim or key in ('B', 'I') else '(超出)'
        head.append(f'| {key} | {title} | {size} | {lim}{flag} |')
    head = [h for h in head if h is not None]
    head.append('')
    return '\n'.join(head) + '\n' + '\n'.join(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('vol')
    ap.add_argument('n', type=int)
    ap.add_argument('--精簡', action='store_true', dest='compact')
    ap.add_argument('--stdout', action='store_true')
    a = ap.parse_args()
    if a.vol not in L.VOLS:
        raise SystemExit(f'卷名須為 {L.VOLS}')
    text = build(a.vol, a.n, a.compact)
    if a.stdout:
        print(text)
        return
    outdir = L.p('正文', '包', a.vol)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f'第{a.n:02d}章.包{"_精簡" if a.compact else ""}.md')
    with open(out, 'w', encoding='utf8') as f:
        f.write(text)
    print(f'已寫入 {L.rel(out)}({len(text)} 字)')


if __name__ == '__main__':
    main()
