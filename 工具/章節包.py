#!/usr/bin/env python3
"""單章上下文包(階段 G1)。把寫一章正文需要的、散在各處的正本資料,依「限知」原則組成一份 Markdown。

用法:
  python3 工具/章節包.py 第一部 3                 # 輸出到標準輸出
  python3 工具/章節包.py 第一部 3 --out 檔案.md    # 寫成檔案(放在專案之外或暫存區,不要提交)

只讀、不改任何專案檔案;輸出不進版本庫(每次現組,不會過期)。

限知原則(對應 正文/寫作規範.md 第十節「與既有設定正本的分工」):
  - 角色狀態與知情矩陣取「上一卷結束」的快照,不取更晚的時點,避免把後面的劇情洩進這一章;
    卷內的變化由角色記憶檔中「與本章事件相關」的段落補上。序卷沒有前卷快照,以大綱與角色設定為準。
  - 事件描述只取本章的對應事件與提及事件。
  - 前章只取:大綱的「結尾與銜接」、(若已寫成)前章正文結尾、(若有)章末狀態摘要。
包內每一節的來源都標在標題上,資料缺漏處寫明「(無)」,不替它補內容。
"""
import glob, os, re, sys

sys.dont_write_bytecode = True

VOLS = ['序卷', '第一部', '第二部', '第三部']
PREFIX = {'PRO': '序卷', 'P1': '第一部', 'P2': '第二部', 'P3': '第三部'}
ID = re.compile(r'(?<![A-Za-z0-9])(?:PRO|P[123])-\d+(?!\d)')
TAIL = 1200          # 前章正文結尾取的字數
ANCHOR_CAP = 3000    # 文風錨點上限
SCENE_CAP = 1800     # 單一場景建模上限


def read(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def field(text, label):
    m = re.search(r'- \*\*' + label + r'\*\*:(.*)', text)
    return m.group(1).strip() if m else ''


def outline_path(vol, n):
    r = sorted(glob.glob(f'故事線/{vol}/章節/{n:02d}_*.md'))
    return r[0] if r else ''


def chapters_of(vol):
    return sorted(int(m.group(1)) for p in glob.glob(f'故事線/{vol}/章節/*_第*章_*.md')
                  if (m := re.match(r'(\d+)_', os.path.basename(p))))


def prev_chapter(vol, n):
    """回傳 (卷, 章) 或 None;第 1 章的前章是上一卷的最後一章。"""
    if n > 1 and outline_path(vol, n - 1):
        return vol, n - 1
    i = VOLS.index(vol)
    if n == 1 and i > 0:
        pv = VOLS[i - 1]
        ch = chapters_of(pv)
        if ch:
            return pv, ch[-1]
    return None


def blocks(text, pat=r'### '):
    """把 ### 小節切成 [(標題, 內容)]。"""
    out = []
    for m in re.finditer(r'^' + pat + r'([^\n]*)\n(.*?)(?=^### |^## |\Z)', text, re.M | re.S):
        out.append((m.group(1).strip(), m.group(2).rstrip()))
    return out


def event_block(eid):
    vol = PREFIX.get(eid.split('-')[0])
    t = read(f'故事線/{vol}/事件描述.md') if vol else ''
    m = re.search(r'### ' + re.escape(eid) + r' [^\n]+\n.*?(?=\n### |\Z)', t, re.S)
    return m.group(0).strip() if m else f'### {eid}\n(事件描述查無此 ID)'


def flat(text):
    """嵌入內容裡的標題改成粗體行,免得和包本身的章節標題混在一起。"""
    return re.sub(r'^#{1,6}\s*(.*)$', r'**\1**', text, flags=re.M)


def section(out, title, body):
    out.append(f'\n## {title}\n')
    out.append(flat(body.strip()) if body and body.strip() else '(無)')


def cast_of(outline_file, text):
    """出場角色 → [(名稱, 角色根目錄)];男主、女主、主要角色。"""
    res = []
    for name, path in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', field(text, '出場角色')):
        if '角色/' not in path:
            continue
        root = os.path.normpath(os.path.join(os.path.dirname(outline_file), path))
        if os.path.isdir(root):
            res.append((name, root))
    return res


def table_rows(text):
    return [l for l in text.split('\n') if l.startswith('|')]


def snapshot_rows(prev_vol, names):
    t = read(f'狀態/{prev_vol}結束/角色狀態.md')
    rows = table_rows(t)
    if not rows:
        return ''
    keep = rows[:2]
    miss = []
    for n in names:
        hit = [r for r in rows[2:] if r.split('|')[1].strip() == n]
        keep += hit
        if not hit:
            miss.append(n)
    out = '\n'.join(keep)
    if miss:
        out += '\n\n快照無此人(查角色設定):' + '、'.join(miss)
    return out


def matrix_section(prev_vol, names):
    t = read('狀態/秘密知情矩陣.md')
    for head in (f'## {prev_vol}結束', f'## 歷史:{prev_vol}結束'):
        m = re.search(re.escape(head) + r'\n(.*?)(?=\n## |\Z)', t, re.S)
        if m:
            break
    else:
        return ''
    rows = table_rows(m.group(1))
    if len(rows) < 3:
        return ''
    cols = [c.strip() for c in rows[0].strip('|').split('|')]
    want = [i for i, c in enumerate(cols) if i < 2 or c in names or c in ('男主', '女主')]
    def pick(r):
        c = [x.strip() for x in r.strip('|').split('|')]
        return '| ' + ' | '.join(c[i] for i in want if i < len(c)) + ' |'
    return '\n'.join([pick(rows[0]), '|' + '---|' * len(want)] + [pick(r) for r in rows[2:]])


def profile(name, root, vol):
    """設定檔的要點(主要角色);男女主取初始個性。"""
    if name in ('男主', '女主'):
        t = read(f'{root}/個性/初始個性.md')
        t = re.sub(r'## 價值觀變化方向\n.*?(?=\n## |\Z)', '', t, flags=re.S)  # 全書弧線,不進單章包
        return f'(取自 {root}/個性/初始個性.md,略去「價值觀變化方向」)\n' + t.strip()
    for v in [vol] + [x for x in reversed(VOLS[:VOLS.index(vol)])]:
        t = read(f'{root}/設定/{v}.md')
        if t:
            keys = ('身份', '外表', '初始個性', '戰力', '武學', '其他專長')
            lines = [f'- **{k}**:{field(t, k)}' for k in keys if field(t, k)]
            sup = re.search(r'## 正文補充.*?\n(.*?)(?=\n## |\Z)', t, re.S)
            if sup:
                lines.append('- 正文補充:\n' + sup.group(1).strip())
            return f'(取自 {root}/設定/{v}.md)\n' + '\n'.join(lines)
    return ''


def memory_blocks(root, vol, ids):
    """角色記憶檔中與本章事件相關的小節,加上它的前一節(補足脈絡)。"""
    t = read(f'{root}/成長/記憶/{vol}.md')
    bl = blocks(t)
    out = []
    for i, (h, b) in enumerate(bl):
        if set(ID.findall(h)) & ids:
            if i > 0 and bl[i - 1] not in out:
                out.append(bl[i - 1])
            out.append((h, b))
    return '\n\n'.join(f'### {h}\n{b}' for h, b in out)


def personality_blocks(root, vol, ids):
    t = read(f'{root}/成長/個性/{vol}.md')
    out = [f'### {h}\n{b}' for h, b in blocks(t) if set(ID.findall(h + b)) & ids]
    return '\n\n'.join(out)


def filtered_lines(path, ids, header_rows=2):
    t = read(path)
    rows = table_rows(t)
    return '\n'.join(rows[:header_rows] + [r for r in rows[header_rows:] if set(ID.findall(r)) & ids]) \
        if any(set(ID.findall(r)) & ids for r in rows[header_rows:]) else ''


def facts_for(keywords, cap=15):
    rows = [l for l in read('設計規範/事實登錄.md').split('\n') if l.startswith('| FACT-')]
    hit = [r for r in rows if any(k and k in r for k in keywords)]
    return '\n'.join(hit[:cap]) + (f'\n(另有 {len(hit) - cap} 條相符未列,見事實登錄)' if len(hit) > cap else '')


def glossary():
    rows = [l for l in read('設計規範/術語表.md').split('\n') if l.startswith('|')][2:]
    out = []
    for r in rows:
        c = [x.strip() for x in r.strip('|').split('|')]
        if len(c) >= 3 and c[2]:
            out.append(f'- 用「{c[0]}」,不用 {c[2]}')
    return '\n'.join(out)


def supplements(vol, n):
    """正文補充登記中,本卷第 1 至 n 章的條目(其他卷不取)。序卷沿用無卷名前綴的舊標題。"""
    t = read('正文/README.md')
    m = re.search(r'## 正文補充登記\n(.*?)(?=\n## |\Z)', t, re.S)
    if not m:
        return ''
    pre = r'(?:' + vol + r'[·・ ]*)' + ('?' if vol == '序卷' else '')
    out = []
    for h, b in blocks(m.group(1)):
        hm = re.match(pre + r'第 (\d+) 章', h)
        if hm and int(hm.group(1)) <= n:
            out.append(f'### {h}\n{b}')
        elif h == '與章節大綱的出入':
            lines = [l for l in b.split('\n') if (lm := re.match(r'- ' + pre + r'第 (\d+) 章', l)) and int(lm.group(1)) <= n]
            if lines:
                out.append('### 與章節大綱的出入\n' + '\n'.join(lines))
        elif h == '人物與稱呼':
            out.append(f'### {h}\n{b}')
    return '\n\n'.join(out)


def prev_summary(vol, n, limit=2):
    """章末狀態摘要:取本章之前最近 limit 章(含跨卷第一章往前一卷)。"""
    out, cur = [], prev_chapter(vol, n)
    while cur and len(out) < limit:
        v, k = cur
        for h, b in blocks(read(f'正文/前情摘要/{v}.md'), r'## '):
            if re.match(r'第 ' + str(k) + r' 章', h):
                out.append(f'### {v}·{h}\n{b}')
                break
        cur = prev_chapter(v, k)
    return '\n\n'.join(reversed(out))


def prev_tail(pv, pk):
    for f in glob.glob(f'正文/{pv}/第{pk}章_*.md'):
        txt = read(f).rstrip()
        return f'(取自 {f},末 {TAIL} 字)\n\n…' + txt[-TAIL:]
    return ''


def prev_points(outline_file):
    """前章正文尚未寫成時的替代:取前章大綱的「情節要點」與「注意事項」,供本章與前章逐項對齊。"""
    t = read(outline_file)
    parts = []
    for h in ('情節要點', '注意事項'):
        m = re.search(r'## ' + h + r'\n(.*?)(?=\n## |\Z)', t, re.S)
        if m and m.group(1).strip():
            parts.append(f'**{h}**\n{m.group(1).strip()}')
    return '\n\n'.join(parts)


def ending_of(outline_file):
    t = read(outline_file)
    m = re.search(r'## 結尾與銜接\n(.*?)(?=\n## |\Z)', t, re.S)
    return m.group(1).strip() if m else ''


def anchors():
    """只取「目前錨點」一節,去掉註解;尚無錨點時回傳空字串。"""
    m = re.search(r'## 目前錨點\n(.*?)(?=\n## |\Z)', read('正文/文風錨點.md'), re.S)
    body = re.sub(r'<!--.*?-->', '', m.group(1), flags=re.S).strip() if m else ''
    return '' if not body or body.startswith('(尚無') else body[:ANCHOR_CAP]


def build(vol, n):
    of = outline_path(vol, n)
    if not of:
        sys.exit(f'找不到 故事線/{vol}/章節/{n:02d}_*.md')
    ot = read(of)
    head = ot.split('\n')[0].lstrip('# ').strip()
    ev = ID.findall(field(ot, '對應事件'))
    mention = ID.findall(field(ot, '提及事件'))
    ids = set(ev)
    cast = cast_of(of, ot)
    names = [c[0] for c in cast]
    pc = prev_chapter(vol, n)
    prev_vol = VOLS[VOLS.index(vol) - 1] if VOLS.index(vol) > 0 else None
    out = [f'# 單章上下文包 · {vol} {head}',
           f'\n> 由 `工具/章節包.py {vol} {n}` 現組,只讀;資料以各正本為準。寫作品質依 [正文/寫作規範.md](正文/寫作規範.md);'
           '寫作用 `jinyong-prose-style`。']

    section(out, f'一、本章大綱(來源:{of})', ot)
    section(out, '二、對應事件描述(演出)', '\n\n'.join(event_block(e) for e in ev))
    section(out, '三、提及事件描述(口述或回想,不演出)', '\n\n'.join(event_block(e) for e in mention))
    section(out, '四、前章銜接', '\n\n'.join(x for x in (
        f'前章 {pc[0]}·第 {pc[1]} 章大綱的「結尾與銜接」:\n' + ending_of(outline_path(*pc)) if pc else '',
        prev_tail(*pc) if pc else '',
        ('(前章正文尚未寫成;以下是前章大綱的要點,本章須與之逐項對齊,細節與本章大綱衝突時先查前章大綱)\n\n' + prev_points(outline_path(*pc))) if pc and not prev_tail(*pc) else '',
        prev_summary(vol, n)) if x))
    if prev_vol:
        section(out, f'五、出場者的卷初狀態(來源:狀態/{prev_vol}結束/角色狀態.md;卷內變化見第七節)', snapshot_rows(prev_vol, names))
        section(out, f'六、秘密知情(來源:狀態/秘密知情矩陣.md,{prev_vol}結束時點)', matrix_section(prev_vol, names))
    else:
        section(out, '五、出場者的卷初狀態', '序卷沒有前卷快照;以章節大綱與下列角色設定為準。')
        section(out, '六、秘密知情', '序卷沒有前卷時點;知識交代見 故事線/序卷/知識交代.md。')
    parts = []
    for name, root in cast:
        pr = profile(name, root, vol)
        mem = memory_blocks(root, vol, ids)
        per = personality_blocks(root, vol, ids)
        if pr or mem or per:
            parts.append(f'### {name}\n' + '\n\n'.join(x for x in (
                pr, ('**記憶(與本章事件相關,含前一節)**\n\n' + mem) if mem else '',
                ('**個性轉變**\n\n' + per) if per else '') if x))
    section(out, '七、出場角色:設定、本卷記憶與個性', '\n\n'.join(parts))
    scenes = []
    for sname, path in re.findall(r'\[([^\]]+)\]\(([^)]+建模描述\.md)\)', field(ot, '場景')):
        sp = os.path.normpath(os.path.join(os.path.dirname(of), path))
        txt = read(sp)
        scenes.append(f'### {sname}(來源:{sp})\n' + (txt.strip()[:SCENE_CAP] if txt else '(無建模)'))
    section(out, '八、場景', '\n\n'.join(scenes))
    section(out, '九、本章相關的伏筆', filtered_lines('狀態/伏筆登記簿.md', ids | set(mention)))
    section(out, '十、本章招式出場(來源:武學設定/招式/' + vol + '招式錄.md)', filtered_lines(f'武學設定/招式/{vol}招式錄.md', ids))
    kw = [x for x in names if x not in ('男主', '女主')] + [s for s, _ in re.findall(r'\[([^\]]+)\]\(([^)]+建模描述\.md)\)', field(ot, '場景'))]
    section(out, '十一、相關硬規則(事實登錄中提到本章角色或場景的條目;全文見 設計規範/事實登錄.md)', facts_for(kw))
    section(out, '十二、用詞(術語表「避免寫法」)', glossary())
    section(out, '十三、本卷已登記的正文補充(第 1 至 ' + str(n) + ' 章)', supplements(vol, n))
    section(out, '十四、文風錨點(正文/文風錨點.md「目前錨點」)', anchors())
    out.append('\n## 十五、動筆與收尾\n')
    out.append('- 寫完先用 `python3 工具/句式掃描.py` 看提示;再登記「正文補充登記」與「與章節大綱的出入」;')
    out.append('- 寫章末狀態摘要到 `正文/前情摘要/' + vol + '.md`;由另一個 session 依 `正文/章後核對.md` 做事實核對。')
    return '\n'.join(out) + '\n'


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    dest = argv[argv.index('--out') + 1] if '--out' in argv else None
    if dest in args:
        args.remove(dest)
    if len(args) != 2 or args[0] not in VOLS or not args[1].isdigit():
        sys.exit('用法:python3 工具/章節包.py {序卷|第一部|第二部|第三部} 章號 [--out 檔案]')
    text = build(args[0], int(args[1]))
    if dest:
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'已寫入 {dest}({len(text)} 字元)')
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main(sys.argv[1:])
