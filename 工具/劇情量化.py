#!/usr/bin/env python3
"""劇情量化:把劇情骨幹當成一個系統來量測,回答「夠不夠好」。只讀,不改任何檔案。

用法:
  python3 工具/劇情量化.py                  # 報告印到標準輸出
  python3 工具/劇情量化.py --out 檔案.md     # 寫成檔案
  python3 工具/劇情量化.py --strict         # 有硬不變量違反時結束碼為 1(預設恆為 0)
  python3 工具/劇情量化.py --裁定表         # 印出 DEC-074 逐章裁定的工作表(朝堂傾向過半的章)

量測的是結構化資料(時間線、事件描述、章節大綱、伏筆登記簿、知情矩陣、狀態快照),不是文筆。
指標的定義、證據等級與「夠好」的驗收標準見 設計規範/劇情基準.md(正本);
「基準區間」只讀取該檔中證據明確的條目,沒有證據的指標只列數字,不下判斷。

指標分組(軟體工程視角):
  A 規模與容量   B 耦合與依賴(角色圖)   C 狀態管理(秘密、伏筆)   D 負載與節奏
  E 難度曲線     F 需求符合度(DEC-074 主軸)   G 改編就緒度(事件契約、場景與角色視覺資料)
  H 驗收(硬不變量)
"""
import collections, glob, os, re, statistics, sys

sys.dont_write_bytecode = True

VOLS = ['序卷', '第一部', '第二部', '第三部']
PREFIX = {'PRO': '序卷', 'P1': '第一部', 'P2': '第二部', 'P3': '第三部'}
ID = re.compile(r'(?<![A-Za-z0-9])(?:PRO|P[123])-\d+(?!\d)')
LEADS = ('男主', '女主')
# DEC-074「主軸在江湖而非廟堂」的操作化(啟發式,可在此調整)。DEC-074 定義的廟堂是「朝堂、東宮、宦官機構與朝史」,
# 黑衣衛、血月教、驛站、幫會等被明列為江湖,故不納入。三個訊號任一成立即判為「朝堂傾向」:
COURT_KEYS = ('朝堂', '皇城', '東宮', '行在', '祭天壇', '皇宮')     # 場景名含關鍵字
COURT_FACTIONS = ('大昭皇室', '內侍監', '清流', '觀星監')            # 出場勢力(勢力/README 標為朝廷、宦官機構、士大夫朋黨、司天機構者)
COURT_TAGS = ('權謀',)                                               # 標籤表:「朝堂、勢力的算計」
EXPECTED_FIELDS = ['序號', '時間', '章節', '場景', '描述', '出場角色']
CONTRACT_FIELDS = ['目標', '衝突', '結果']   # 改編(動畫、遊戲)需要、但目前事件描述沒有的欄位


def read(p):
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def table(text):
    return [[c.strip() for c in l.strip().strip('|').split('|')] for l in text.split('\n') if l.startswith('|')]


def norm(n):
    return '懷虛子' if n.startswith('懷虛子') else n


# ---------- 資料載入 ----------

def outline_files(vol):
    return sorted(glob.glob(f'故事線/{vol}/章節/[0-9][0-9]_第*章_*.md'))


def chapter_count(vol):
    return len(outline_files(vol))


def offsets():
    off, acc = {}, 0
    for v in VOLS:
        off[v] = acc
        acc += chapter_count(v)
    return off


OFF = offsets()


def load_timeline(vol):
    rows = []
    for c in table(read(f'故事線/{vol}/時間線.md')):
        if len(c) >= 9 and c[0].isdigit() and ID.fullmatch(c[1]):
            raw = c[8]
            m = re.match(r'第 (\d+) 章(\(提及\))?', raw)
            kind, ch = ('提及' if m.group(2) else '演出', int(m.group(1))) if m else ('背景', 0)
            rows.append({'seq': int(c[0]), 'id': c[1], 'rel': c[2], 'tags': [t for t in re.split('[、,]', c[3]) if t],
                         'love': c[4], 'name': c[5], 'kind': kind, 'ch': ch, 'vol': vol})
    return rows


def load_events(vol):
    out = {}
    for m in re.finditer(r'### ([A-Z0-9]+-\d+) ([^\n]+)\n(.*?)(?=\n### |\Z)', read(f'故事線/{vol}/事件描述.md'), re.S):
        body = m.group(3)
        fields = re.findall(r'^- \*\*([^*]+)\*\*:', body, re.M)
        sl = re.search(r'^- \*\*場景\*\*:(.*)', body, re.M)
        scenes = []
        if sl:
            line = sl.group(1).strip()
            scenes = [(n, False) for n, _ in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', line)]
            if line.startswith('待建:'):
                scenes = [(s.strip(), True) for s in re.split('[、,]', line[3:]) if s.strip()]
        cl = re.search(r'^- \*\*出場角色\*\*:(.*)', body, re.M)
        chars, facs = [], []
        for n, p in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', cl.group(1) if cl else ''):
            (chars if '角色/' in p else facs if '勢力/' in p else []).append(norm(n))
        out[m.group(1)] = {'title': m.group(2), 'fields': fields, 'scenes': scenes, 'chars': chars, 'facs': facs}
    return out


def chapter_info(vol):
    info = {}
    for f in outline_files(vol):
        m = re.match(r'(\d+)_第\d+章_(.+)\.md', os.path.basename(f))
        t = read(f)
        pov = re.search(r'- \*\*視角\*\*:(.*)', t)
        info[int(m.group(1))] = {'title': m.group(2), 'pov': pov.group(1).strip() if pov else '', 'wan': None}
    for row in table(read(f'故事線/{vol}/章節/README.md')):
        m = re.match(r'第 (\d+) 章', row[0]) if row else None
        if m and int(m.group(1)) in info:
            w = re.search(r'([\d.]+) 萬', row[-1])
            info[int(m.group(1))]['wan'] = float(w.group(1)) if w else None
    return info


def tag_types():
    t = {}
    for c in table(read('設計規範/標籤表.md')):
        if len(c) >= 3 and c[2] in ('緩衝', '推進', '重'):
            t[c[0]] = c[2]
    return t


def event_type(tags, tt):
    ts = {tt.get(x) for x in tags}
    return '重' if '重' in ts else '推進' if '推進' in ts else '緩衝'


def gidx(vol, ch):
    return OFF[vol] + ch


def load_all():
    tl, ev, ci = {}, {}, {}
    for v in VOLS:
        tl[v], ev[v], ci[v] = load_timeline(v), load_events(v), chapter_info(v)
    pos = {}
    for v in VOLS:
        for r in tl[v]:
            pos[r['id']] = (gidx(v, r['ch']), r['seq'], v, r['kind'])
    return tl, ev, ci, pos


def snapshots():
    out = {}
    for v in VOLS:
        rows = table(read(f'狀態/{v}結束/角色狀態.md'))
        if len(rows) < 3:
            continue
        head = rows[0]
        li = next((i for i, h in enumerate(head) if '戰力' in h), None)
        ai = next((i for i, h in enumerate(head) if h == '生死'), None)
        d = {}
        for r in rows[2:]:
            if li is not None and len(r) > li:
                m = re.match(r'L(\d+)', r[li])
                if m:
                    d[norm(r[0])] = (int(m.group(1)), r[ai] if ai is not None and len(r) > ai else '')
        out[v] = d
    return out


# ---------- 指標計算 ----------

def stats(xs):
    if not xs:
        return '—'
    xs = sorted(xs)
    return f'中位 {statistics.median(xs):g}、最大 {xs[-1]:g}、最小 {xs[0]:g}(n={len(xs)})'


def bench():
    """讀 設計規範/劇情基準.md「基準區間(機器讀取)」:| 指標 | 下限 | 上限 | 證據 |"""
    t = read('設計規範/劇情基準.md')
    m = re.search(r'## (?:[一二三四五六七八九十]+、)?基準區間\(機器讀取\)\n(.*?)(?=\n## |\Z)', t, re.S)
    out = {}
    for c in table(m.group(1) if m else ''):
        if len(c) >= 4 and re.fullmatch(r'[A-Z]\d', c[0]):
            try:
                out[c[0]] = (float(c[1]), float(c[2]), c[3])
            except ValueError:
                pass
    return out


def judge(key, value, bm):
    if key not in bm:
        return ''
    lo, hi, ev = bm[key]
    return f"{'✓' if lo <= value <= hi else '✗'}(參考 {lo:g}–{hi:g};{ev})"


def main(argv):
    tl, ev, ci, pos = load_all()
    tt = tag_types()
    snaps = snapshots()
    bm = bench()
    out, hard = [], []
    P = out.append

    P('# 劇情量化報告\n')
    P('> 由 `python3 工具/劇情量化.py` 產生,只讀。指標定義、證據等級與驗收標準見 [劇情基準](../設計規範/劇情基準.md)。')
    P('> 量測的是結構化資料,不是文筆。沒有證據的指標只列數字,不下判斷。\n')

    # A 規模
    P('## A 規模與容量\n')
    P('| 卷 | 章數 | 預計字數(萬) | 章均字數(萬) | 事件總數 | 演出事件 | 提及 | 背景 | 演出事件/章 |')
    P('|---|---|---|---|---|---|---|---|---|')
    total_wan, total_ch = 0.0, 0
    for v in VOLS:
        n = chapter_count(v)
        wans = [c['wan'] for c in ci[v].values() if c['wan']]
        wan = sum(wans)
        kinds = collections.Counter(r['kind'] for r in tl[v])
        total_wan += wan
        total_ch += n
        P(f"| {v} | {n} | {wan:.1f} | {wan / n:.2f} | {len(tl[v])} | {kinds['演出']} | {kinds['提及']} | {kinds['背景']} | {kinds['演出'] / n:.2f} |")
    P(f'| 合計 | {total_ch} | {total_wan:.1f} | {total_wan / total_ch:.2f} | {sum(len(tl[v]) for v in VOLS)} | | | | |\n')
    for v in VOLS[1:]:
        n = chapter_count(v)
        wans = [c['wan'] for c in ci[v].values() if c['wan']]
        P(f"- A1 每部章數 · {v}:{n} {judge('A1', n, bm)}")
        P(f"- A2 章均字數(萬) · {v}:{sum(wans) / n:.2f} {judge('A2', sum(wans) / n, bm)}")
    P('')

    # B 耦合
    P('## B 耦合與依賴(角色共現圖)\n')
    P('以「同一演出事件的出場角色」為邊(只計有連結的角色)。')
    P('| 範圍 | 角色數 | 邊數 | 男女主佔邊 | 去除男女主後連通塊 | 去除後最大塊佔比 | 只出場 1 次 | 出場≥2 次(群像) |')
    P('|---|---|---|---|---|---|---|---|')
    for scope in VOLS + ['全書']:
        vols = VOLS if scope == '全書' else [scope]
        adj, app = collections.defaultdict(set), collections.Counter()
        for v in vols:
            for r in tl[v]:
                if r['kind'] != '演出' or r['id'] not in ev[v]:
                    continue
                cs = sorted(set(ev[v][r['id']]['chars']))
                for a in cs:
                    app[a] += 1
                    adj[a]
                for i, a in enumerate(cs):
                    for b in cs[i + 1:]:
                        adj[a].add(b)
                        adj[b].add(a)
        edges = {frozenset((a, b)) for a in adj for b in adj[a]}
        lead_edges = sum(1 for e in edges if e & set(LEADS))
        rest = {a for a in adj if a not in LEADS}
        seen, comps = set(), []
        for s in rest:
            if s in seen:
                continue
            comp, stack = set(), [s]
            while stack:
                x = stack.pop()
                if x in comp:
                    continue
                comp.add(x)
                stack += [y for y in adj[x] if y in rest and y not in comp]
            seen |= comp
            comps.append(len(comp))
        big = max(comps) / len(rest) if rest else 0
        P(f"| {scope} | {len(adj)} | {len(edges)} | {lead_edges / len(edges):.0%} | {len(comps)} | {big:.0%} | "
          f"{sum(1 for a in app if app[a] == 1)} | {sum(1 for a in app if app[a] >= 2)} |" if edges else f'| {scope} | {len(adj)} | 0 | — | — | — | — | — |')
    P('\n- 「去除男女主後連通塊」越多、最大塊佔比越低,代表世界越依賴男女主才連得起來(單點依賴);越少代表配角之間自成網絡。')
    P('')

    # C 狀態管理
    P('## C 狀態管理\n')
    P('### C1 秘密:男女主何時得知(來源:知情矩陣各時點)\n')
    mt = read('狀態/秘密知情矩陣.md')
    sections = {}
    for v in VOLS:
        m = re.search(r'## (?:歷史:)?' + v + r'結束\n(.*?)(?=\n## |\Z)', mt, re.S)
        if m:
            sections[v] = table(m.group(1))
    P('| 時點 | 秘密總數 | 男主已知 | 女主已知 | 男主知而女主不知 | 女主知而男主不知 |')
    P('|---|---|---|---|---|---|')

    def knows(cell):
        return cell.startswith('知') or cell.startswith('部分知')
    for v in VOLS:
        rows = sections.get(v)
        if not rows or len(rows) < 3:
            continue
        head = rows[0]
        if '男主' not in head or '女主' not in head:
            continue
        hi, fi = head.index('男主'), head.index('女主')
        body = [r for r in rows[2:] if len(r) > max(hi, fi) and r[0].startswith('SEC-')]
        hk = sum(knows(r[hi]) for r in body)
        fk = sum(knows(r[fi]) for r in body)
        P(f"| {v}結束 | {len(body)} | {hk} | {fk} | {sum(knows(r[hi]) and not knows(r[fi]) for r in body)} | {sum(knows(r[fi]) and not knows(r[hi]) for r in body)} |")
    P('\n- 「男知女不知」與「女知男不知」是戲劇張力的資訊差庫存;全為 0 表示兩人永遠同步,少了資訊差的戲。\n')

    P('### C2 伏筆:設置到回收的距離(以章為單位,跨卷累計排序)\n')
    rows = [r for r in table(read('狀態/伏筆登記簿.md')) if r and re.fullmatch(r'THR-\d+', r[0])]
    dist, bad_order, no_recover, no_set, single_long = [], [], [], [], []
    for r in rows:
        sets = [pos[i] for i in ID.findall(r[2]) if i in pos]
        recs = [pos[i] for i in ID.findall(r[3]) if i in pos]
        if not recs:
            no_recover.append(r[0])
            continue
        if not sets:
            if not re.search(r'典籍|世界設定|—', r[2]):
                no_set.append(r[0])
            continue
        d = min(x[0] for x in recs) - max(x[0] for x in sets)
        if d < 0:
            bad_order.append(f'{r[0]}(設置在全書第 {max(x[0] for x in sets)} 章,回收在第 {min(x[0] for x in recs)} 章)')
        dist.append((d, r[0], r[1]))
        if d >= 40 and len(sets) == 1:
            single_long.append(f'{r[0]}({d} 章)')
    ds = [d for d, _, _ in dist]
    P(f'- 伏筆總數 {len(rows)};可計算距離 {len(dist)};距離(章):{stats(ds)}')
    if ds:
        P(f"- 同章或相鄰章(≤1)回收:{sum(1 for d in ds if d <= 1)};跨過 20 章以上:{sum(1 for d in ds if d >= 20)};跨過 60 章以上:{sum(1 for d in ds if d >= 60)}")
        P('- 距離最長的 5 條:' + ';'.join(f'{i} {t[:14]}({d} 章)' for d, i, t in sorted(dist, reverse=True)[:5]))
        P(f"- 距離 ≥40 章、卻只有單一設置點(中途沒有再次設置或呼應,讀者容易遺忘)的伏筆:{len(single_long)} 條 — " + ('、'.join(single_long) or '無'))
    P('')

    # D 負載與節奏
    streaks = {}
    P('## D 負載與節奏(演出事件,依事件標籤的類型:緩衝/推進/重)\n')
    P('| 卷 | 緩衝 | 推進 | 重 | 最長連續無緩衝(事件數) | 第一個「重」的位置 | 「重」事件的十等分分布 | 末三分之一章的事件密度/全卷 |')
    P('|---|---|---|---|---|---|---|---|')
    for v in VOLS:
        evs = [r for r in tl[v] if r['kind'] == '演出']
        if not evs:
            continue
        types = [event_type(r['tags'], tt) for r in evs]
        c = collections.Counter(types)
        run = best = 0
        best_end = -1
        for k, t in enumerate(types):
            run = run + 1 if t != '緩衝' else 0
            if run > best:
                best, best_end = run, k
        streaks[v] = (best, evs[best_end - best + 1]['ch'], evs[best_end]['ch']) if best else (0, 0, 0)
        heavy = [i for i, t in enumerate(types) if t == '重']
        hist = [0] * 10
        for i in heavy:
            hist[min(9, i * 10 // len(types))] += 1
        n = chapter_count(v)
        third = n - n // 3
        last = [r for r in evs if r['ch'] > third]
        ratio = (len(last) / max(1, n - third)) / (len(evs) / n)
        first = f'{heavy[0] / len(types):.0%}' if heavy else '—'
        P(f"| {v} | {c['緩衝'] / len(types):.0%} | {c['推進'] / len(types):.0%} | {c['重'] / len(types):.0%} | {best} | {first} | {'/'.join(map(str, hist))} | {ratio:.2f} |")
    P('\n- 末三分之一章的事件密度/全卷 > 1.3 代表收尾段超載(事件擠在最後幾章,容易趕);< 0.7 代表尾段鬆散。')
    P('- 最長連續無緩衝段落的位置:' + ';'.join(f'{v} 第 {a}–{b} 章(連續 {n} 個事件)' for v, (n, a, b) in streaks.items() if n))
    P('')
    P('### D2 視角平衡(章節大綱「視角」欄)\n')
    P('| 卷 | 只男主 | 只女主 | 男女交錯 | 群像或其他 | 單人視角平衡(少/多) |')
    P('|---|---|---|---|---|---|')
    for v in VOLS:
        c = collections.Counter()
        for k, i in ci[v].items():
            p = i['pov']
            has_m, has_f = '男主' in p, '女主' in p
            c['雙' if has_m and has_f else '男' if has_m and '、' not in p else '女' if has_f and '、' not in p else '他'] += 1
        mx, mn = max(c['男'], c['女']), min(c['男'], c['女'])
        P(f"| {v} | {c['男']} | {c['女']} | {c['雙']} | {c['他']} | {mn / mx:.2f} |" if mx else f"| {v} | {c['男']} | {c['女']} | {c['雙']} | {c['他']} | — |")
    P('')

    # E 難度曲線
    P('## E 難度曲線(戰力 L;來源:各卷結束的角色狀態)\n')
    P('| 卷結束 | 男主 L | 女主 L | 本卷出場者(快照內)最高 L | 差距(最高−男主) |')
    P('|---|---|---|---|---|')
    for v in VOLS:
        s = snaps.get(v)
        if not s:
            continue
        cast = {c for r in tl[v] if r['kind'] == '演出' and r['id'] in ev[v] for c in ev[v][r['id']]['chars']} - set(LEADS)
        top = sorted(((s[c][0], c) for c in cast if c in s), reverse=True)[:3]
        hl = s.get('男主', (None,))[0]
        fl = s.get('女主', (None,))[0]
        P(f"| {v} | {hl} | {fl} | " + '、'.join(f'{c} L{l}' for l, c in top) + f" | {top[0][0] - hl if top and hl is not None else '—'} |")
    P('\n- 觀察:男主 L 隨卷上升、對手最高 L 與男主的差距逐步縮小,表示難度曲線單調上升;差距忽大忽小或男主反超過早,表示壓迫感不穩。快照只含部分角色,僅作參考。')
    P('')

    # F 需求符合度
    P('## F 需求符合度:DEC-074「主軸在江湖而非廟堂」\n')
    P(f'操作化(啟發式,在本工具頂端可調):事件的「朝堂傾向」= 標籤含 {"、".join(COURT_TAGS)},或場景名含 {"、".join(COURT_KEYS)},或出場勢力含 {"、".join(COURT_FACTIONS)}。黑衣衛、血月教等被 DEC-074 明列為江湖,不計入。\n')
    P('| 卷 | 演出事件 | 朝堂傾向事件 | 占比 | 朝堂傾向過半的章數 / 全部章數 |')
    P('|---|---|---|---|---|')
    court_chapters = []
    court_detail = collections.defaultdict(list)
    for v in VOLS:
        evs = [r for r in tl[v] if r['kind'] == '演出']

        def courty(r):
            e = ev[v].get(r['id'], {'scenes': [], 'facs': []})
            why = [t for t in r['tags'] if t in COURT_TAGS] + [s for s, _ in e['scenes'] if any(k in s for k in COURT_KEYS)] \
                + [f for f in e['facs'] if f in COURT_FACTIONS]
            return '、'.join(dict.fromkeys(why))
        n_c = sum(bool(courty(r)) for r in evs)
        per = collections.defaultdict(lambda: [0, 0])
        for r in evs:
            per[r['ch']][1] += 1
            if courty(r):
                per[r['ch']][0] += 1
                court_detail[(v, r['ch'])].append(f"{r['id']} {r['name']}({courty(r)})")
        heavy = [(ch, a, b) for ch, (a, b) in sorted(per.items()) if b and a / b >= 0.5]
        for ch, a, b in heavy:
            court_chapters.append((v, ch, ci[v].get(ch, {}).get('title', ''), a, b))
        P(f"| {v} | {len(evs)} | {n_c} | {n_c / max(1, len(evs)):.0%} | {len(heavy)} / {chapter_count(v)} |")
    P('\n朝堂傾向過半的章(供 DEC-074 逐章裁定:保留、改成江湖視角,或縮成遠景):\n')
    P('| 卷·章 | 標題 | 朝堂傾向事件 / 演出事件 |')
    P('|---|---|---|')
    for v, ch, t, a, b in court_chapters:
        P(f'| {v}·第 {ch} 章 | {t} | {a} / {b} |')
    P('')

    # G 改編就緒度
    P('## G 改編就緒度(動畫、遊戲等媒介要從骨幹取用的資料)\n')
    allev = {i: e for v in VOLS for i, e in ev[v].items()}
    P(f'### G1 事件契約欄位覆蓋(共 {len(allev)} 個事件)\n')
    P('| 欄位 | 覆蓋 | 說明 |')
    P('|---|---|---|')
    for f in EXPECTED_FIELDS:
        P(f"| {f} | {sum(f in e['fields'] for e in allev.values()) / len(allev):.0%} | 現有 |")
    for f in CONTRACT_FIELDS:
        cov = sum(f in e['fields'] for e in allev.values()) / len(allev)
        P(f"| {f} | {cov:.0%} | " + ('**缺口**:改編需要的「每個事件的目的、阻力、結果」目前只寫在描述句裡,沒有獨立欄位' if cov == 0 else '補寫中(試點)' if cov < 1 else '完整') + ' |')
    heavy_ids = [r['id'] for v in VOLS for r in tl[v] if r['kind'] == '演出' and event_type(r['tags'], tt) == '重' and r['id'] in ev[v]]
    full = [i for i in heavy_ids if all(f in allev[i]['fields'] for f in CONTRACT_FIELDS)]
    P(f"\n- 「重」類演出事件 {len(heavy_ids)} 個,契約欄位(目標、衝突、結果)齊全的 {len(full)} 個({len(full) / max(1, len(heavy_ids)):.0%})。")
    P('')
    stage = [(v, i) for v in VOLS for r in tl[v] if r['kind'] == '演出' for i in [r['id']] if i in ev[v]]
    pend = collections.Counter(s for v, i in stage for s, p in ev[v][i]['scenes'] if p)
    noscene = sum(1 for v, i in stage if not ev[v][i]['scenes'])
    P('### G2 場景資料\n')
    P(f'- 演出事件 {len(stage)} 個;沒有場景欄位的 {noscene} 個;場景標「待建」的事件 {sum(1 for v, i in stage if any(p for _, p in ev[v][i]["scenes"]))} 個。')
    P('- 待建場景(依事件數):' + ('、'.join(f'{s}×{n}' for s, n in pend.most_common(10)) or '無'))
    P('')
    app = collections.Counter(c for v, i in stage for c in ev[v][i]['chars'])
    miss = []
    for c, n in app.most_common():
        if n < 3:
            break
        if c in LEADS:
            txt = read(f'角色/{c}/個性/初始個性.md')
        else:
            txt = ''.join(read(f) for f in glob.glob(f'角色/主要角色/{c}/設定/*.md'))
        if '外表' not in txt:
            miss.append(f'{c}×{n}')
    P('### G3 角色視覺資料\n')
    P(f'- 演出事件出場 ≥3 次的角色 {sum(1 for c in app if app[c] >= 3)} 人;設定檔沒有「外表」描述的 {len(miss)} 人:' + ('、'.join(miss) or '無'))
    P('')

    # H 驗收
    P('## H 驗收:硬不變量\n')
    P('硬不變量必須為 0 項違反。結構檢查(連結、年齡、感情對稱、已故、凍結等)由 `工具/檢查.py` 負責,這裡只列它沒有涵蓋的。\n')

    def inv(name, items):
        P(f"- {'✓' if not items else '✗'} {name}:{len(items)} 項" + ('' if not items else ' — ' + ';'.join(items[:8]) + ('…' if len(items) > 8 else '')))
        if items:
            hard.append(name)
    inv('H1 每條伏筆都有可解析的回收事件', no_recover)
    inv('H2 每條伏筆的設置事件可解析(或標明典籍、世界設定)', no_set)
    inv('H3 伏筆回收不得早於設置(因果順序)', bad_order)
    unresolved, handoff = [], []
    for v in VOLS:
        t = read(f'故事線/{v}/大綱.md')
        m = re.search(r'## 待(?:後續階段決定|決.*?)\n(.*?)(?=\n## |\Z)', t, re.S)
        if not m:
            continue
        for l in m.group(1).split('\n'):
            is_item = re.match(r'\d+\.', l) or (l.startswith('|') and not re.match(r'\|[-| ]+\|$', l) and '項目' not in l)
            if not is_item or any(k in l for k in ('已定', '已決', '不再追加')):
                continue
            if '正文階段' in l:
                handoff.append(f'{v}:{re.sub(r"[|*]", "", l)[:14].strip()}')
            else:
                unresolved.append(f'{v}:{re.sub(r"[|*]", "", l)[:18].strip()}')
    inv('H4 大綱「待決」表中沒有未裁定項(未標「已定」「已決」)', unresolved)
    P(f"- 移交正文階段、不屬於劇情待決的項目:{len(handoff)} 項" + ('(' + ';'.join(handoff) + ')' if handoff else ''))
    P('\n— 以上為本工具的量測結果;「夠好」的完整驗收標準(含人工關卡)見 [劇情基準](../設計規範/劇情基準.md)。')

    if '--裁定表' in argv:
        w = ['# DEC-074 逐章裁定表\n',
             '> 由 `python3 工具/劇情量化.py --裁定表` 產生的工作表。依據:[DEC-074](設計決定記錄.md) 全書主軸聚焦江湖而非廟堂。',
             '> 「朝堂傾向」是啟發式判定(標籤含權謀、場景為朝堂類、或朝廷類勢力出場),只用來列出候選章,不代表這章一定要改。',
             '> 判定欄「事件(判定理由)」列出本章被判為朝堂傾向的事件。請在「裁定」欄填入下列三者之一,並在「理由」欄寫一句話:',
             '> - **保留**:這章是劇情必需的朝堂戲,維持原樣;',
             '> - **改江湖視角**:事件保留,但改成江湖人的視角或場景來演(例:由黑衣衛、驛站、幫會的眼睛看);',
             '> - **縮成遠景**:事件改為口述或一兩句帶過(章節欄改為「提及」),騰出的篇幅另作安排。',
             '> 裁定後要改動凍結內容,須走[變更傳播](建檔架構與順序.md),並在設計決定記錄新增一條。\n',
             '| 卷·章 | 標題 | 朝堂傾向 / 演出 | 事件(判定理由) | 裁定 | 理由 |',
             '|---|---|---|---|---|---|']
        for v, ch, title, a, b in court_chapters:
            w.append(f"| {v}·第 {ch} 章 | {title} | {a} / {b} | " + ';'.join(court_detail[(v, ch)]) + ' | | |')
        sys.stdout.write('\n'.join(w) + '\n')
        return 0
    text = '\n'.join(out) + '\n'
    dest = argv[argv.index('--out') + 1] if '--out' in argv else None
    if dest:
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'已寫入 {dest}')
    else:
        sys.stdout.write(text)
    return 1 if ('--strict' in argv and hard) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
