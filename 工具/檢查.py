#!/usr/bin/env python3
"""專案一致性檢查。用法:python3 工具/檢查.py(於專案根目錄執行)。有任何問題則結束碼為 1。"""
import glob, os, re, sys, urllib.parse

sys.dont_write_bytecode = True

problems = []


def read(p):
    with open(p, encoding='utf8') as f:
        return f.read()


def add(kind, msg):
    problems.append(f'[{kind}] {msg}')


# 1. 連結
def check_links():
    for f in glob.glob('**/*.md', recursive=True):
        for m in re.finditer(r'\]\(([^)#]+)\)', read(f)):
            l = m.group(1)
            if l.startswith('http'):
                continue
            p = os.path.normpath(os.path.join(os.path.dirname(f), urllib.parse.unquote(l)))
            if not os.path.exists(p):
                add('連結', f'{f} → {l}')


# 角色根目錄
def roots():
    r = {'男主': '角色/男主', '女主': '角色/女主'}
    base = '角色/主要角色'
    for d in os.listdir(base):
        if os.path.isdir(f'{base}/{d}'):
            r[d] = f'{base}/{d}'
    return r


ALIAS = {'母親_溫素問': ['溫素問'], '父親_晏明徽': ['晏明徽'], '外祖_青城': ['溫伯仁'],
         '阿古': ['呼延阿古'], '父母': ['陸驍', '蕭婉']}


# 2. 雙向感情
def check_symmetry(volume='序卷'):
    rs = roots()
    pairs = set()
    for n, r in rs.items():
        cg = f'{r}/成長/感情'
        if not os.path.isdir(cg):
            continue
        for t in os.listdir(cg):
            f = f'{cg}/{t}/{volume}.md'
            if not os.path.exists(f) or '尚未接觸' in read(f):
                continue
            for x in ALIAS.get(t, [t]):
                pairs.add((n, x))
    dead = set()
    snap = sorted(glob.glob('狀態/*結束'))
    if snap:
        dead = set(re.findall(r'^\| (\S+) \| 已故\(', read(f'{snap[-1]}/角色狀態.md'), re.M))
    for a, b in sorted(pairs):
        if b in rs and b not in dead and (b, a) not in pairs:
            add('感情對稱', f'{a}→{b} 有,但 {b}→{a} 沒有({volume})')


# 3. 戰力上限
def check_power_cap():
    for f in glob.glob('角色/**/*.md', recursive=True) + glob.glob('狀態/**/*.md', recursive=True):
        for m in re.finditer(r'L(\d+)', read(f)):
            if int(m.group(1)) > 25:
                add('戰力', f'{f} 出現 L{m.group(1)}(超過世界上限 L25)')


# 4/6. 事件描述解析
def events(volume_dir='故事線/序卷', prefix='PRO'):
    src = read(f'{volume_dir}/事件描述.md')
    out = {}
    for sec in re.split(r'\n(?=### )', src):
        m = re.match(rf'### ({prefix}-\d+) ', sec)
        if not m:
            continue
        line = re.search(r'- \*\*出場角色\*\*:(.*)', sec)
        names = set()
        if line:
            for t in re.finditer(r'\[([^\]]+)\]\(\.\./\.\./角色/', line.group(1)):
                n = t.group(1)
                names.add('懷虛子' if n.startswith('懷虛子') else n)
        out[m.group(1)] = names
    return out


def time_seq(volume_dir):
    """事件 ID → 時間線的序(時間順序)。"""
    out = {}
    p = f'{volume_dir}/時間線.md'
    if os.path.exists(p):
        for line in read(p).split('\n'):
            m = re.match(r'\| (\d+) \| (\w+-\d+) ', line)
            if m:
                out[m.group(2)] = int(m.group(1))
    return out


def check_events(volume='序卷', volume_dir='故事線/序卷', prefix='PRO'):
    ev = events(volume_dir, prefix)
    rs = roots()
    # 連號
    nums = sorted(int(k.split('-')[1]) for k in ev)
    if nums != list(range(1, len(nums) + 1)):
        add('事件', f'{prefix} 編號不連續')
    # 事件覆蓋:出場者的記憶檔需含該事件 ID
    for eid, names in ev.items():
        for n in names:
            if n not in rs:
                add('事件', f'{eid} 出場角色「{n}」找不到角色資料夾')
                continue
            f = f'{rs[n]}/成長/記憶/{volume}.md'
            if os.path.exists(f) and eid not in read(f):
                add('事件覆蓋', f'{eid} 的出場者「{n}」記憶檔未列此事件')
    # 已故角色不得出現在死後事件
    snap = sorted(glob.glob('狀態/*結束'))
    if snap:
        text = read(f'{snap[-1]}/角色狀態.md')
        for m in re.finditer(r'^\| (\S+) \| 已故\((\w+-\d+)\)', text, re.M):
            who, death = m.group(1), m.group(2)
            for eid, names in ev.items():
                if who not in names:
                    continue
                # 死於前一卷者,本卷任何事件都不得出場;同卷者比較事件編號
                order = ['PRO', 'P1', 'P2', 'P3']
                dv, ev_ = order.index(death.split('-')[0]), order.index(prefix)
                # 同卷以時間線的「序」比較(後加入的事件編號不依時間);沒有時間線時才比較編號
                sq = time_seq(volume_dir)
                later = (sq[eid] > sq[death]) if (eid in sq and death in sq) else int(eid.split('-')[1]) > int(death.split('-')[1])
                if dv < ev_ or (dv == ev_ and later):
                    add('已故', f'{who} 於 {eid} 出場,晚於死亡事件 {death}')
    # 本卷內死亡:年齡表標「已故(本卷事件)」者,不得出現在晚於死亡事件的事件
    ap = f'{volume_dir}/年齡表.md'
    if os.path.exists(ap):
        sq = time_seq(volume_dir)
        for line in read(ap).split('\n'):
            c = [x.strip() for x in line.strip().strip('|').split('|')]
            m = re.search(rf'已故\(({prefix}-\d+)\)', c[-1] if c else '')
            if not m or len(c) < 4 or m.group(1) not in sq:
                continue
            for eid, names in ev.items():
                if c[0] in names and eid in sq and sq[eid] > sq[m.group(1)]:
                    add('已故', f'{c[0]} 於 {eid} 出場,晚於年齡表標註的死亡事件 {m.group(1)}')
    # 伏筆登記簿事件存在(序卷)
    tp = '狀態/伏筆登記簿.md'
    if prefix == 'PRO' and os.path.exists(tp):
        for m in re.finditer(r'\b(PRO-\d+)\b', read(tp)):
            if m.group(1) not in ev:
                add('伏筆', f'伏筆登記簿引用不存在的事件 {m.group(1)}')


# 5. 占比
def check_ratio():
    tot = {}
    for f in ['故事大綱/第一部_少年遊.md', '故事大綱/第二部_離亂行.md', '故事大綱/第三部_補天錄.md']:
        c = {}
        for line in read(f).split('\n'):
            m = re.match(r'- 第 (\d+)(?:–(\d+))? 章【(\w+)】', line)
            if m:
                a = int(m.group(1))
                b = int(m.group(2) or a)
                c[m.group(3)] = c.get(m.group(3), 0) + b - a + 1
        n = sum(c.values())
        pct = c.get('同行', 0) / n * 100 if n else 0
        if not 30 <= pct <= 40:
            add('占比', f'{f} 同行占比 {pct:.0f}%(目標 30%–40%)')
        for k, v in c.items():
            tot[k] = tot.get(k, 0) + v


# 8. 角色狀態 L 與成長紀錄一致(以最新快照所屬卷的武學紀錄最後一段為準)
def check_state_power():
    snap = sorted(glob.glob('狀態/*結束'))
    if not snap:
        return
    vol = os.path.basename(snap[-1])[:-2]
    rs = roots()
    for line in read(f'{snap[-1]}/角色狀態.md').split('\n'):
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) < 6 or not cells[5].startswith('L'):
            continue
        name, lv = cells[0], cells[5]
        for p in (f'{rs[name]}/成長/武學/{vol}.md' if name in rs else '', f'角色/主要角色/{name}/設定/{vol}.md'):
            if p and os.path.exists(p):
                ls = re.findall(r'\*\*戰力\*\*:(L\d+)', read(p))
                if ls and ls[-1] != lv:
                    add('戰力', f'{name} 狀態表 {lv} 與 {p} 最後一段 {ls[-1]} 不一致')
                break


# 9. ID 對照
def check_ids():
    t = read('設計規範/ID對照.md')
    ids = {}
    for m in re.finditer(r'^\| ((?:CHR|ORG|LOC)-\d+) \| (.*?) \| `(.*?)` \|', t, re.M):
        i, name, path = m.groups()
        if i in ids:
            add('ID', f'{i} 重複')
        ids[i] = (name, path)
        if not os.path.exists(path):
            add('ID', f'{i} 的路徑不存在:{path}')
            continue
        if i.startswith('CHR'):
            if name in ('男主', '女主'):
                files = [path + 'README.md']
                pat = f'**ID**:{i}'
            else:
                files = glob.glob(path + '設定/*.md')
                pat = f'> ID:{i}'
                if not files:
                    add('ID', f'{i} {name} 沒有設定檔')
        elif i.startswith('ORG'):
            files = [path]
            pat = f'**ID**:{i}'
        else:
            files = [path + '建模描述.md']
            pat = f'**ID**:{i}'
        for f in files:
            if os.path.exists(f) and pat not in read(f):
                add('ID', f'{f} 缺少 {pat}')
    # 反向:資料夾都已登記
    reg = {v[1] for v in ids.values()}
    for d in os.listdir('角色/主要角色'):
        if os.path.isdir(f'角色/主要角色/{d}') and f'角色/主要角色/{d}/' not in reg:
            add('ID', f'角色 {d} 未登記 ID')
    for f in os.listdir('勢力'):
        if f.endswith('.md') and f != 'README.md' and f'勢力/{f}' not in reg:
            add('ID', f'勢力 {f} 未登記 ID')
    for d in os.listdir('世界設定/場景設定'):
        if os.path.isdir(f'世界設定/場景設定/{d}') and f'世界設定/場景設定/{d}/' not in reg:
            add('ID', f'場景 {d} 未登記 ID')


# 10. 術語表:避免寫法
def check_terms():
    t = read('設計規範/術語表.md')
    bad = []
    for line in t.split('\n'):
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) == 3 and cells[2] and cells[0] not in ('標準寫法', '---'):
            for w in cells[2].split('、'):
                bad.append((w.strip(), cells[0]))
    for f in glob.glob('**/*.md', recursive=True):
        if f.endswith('設計規範/術語表.md'):
            continue
        txt = read(f)
        for w, std in bad:
            if w and w in txt:
                add('術語', f'{f} 使用「{w}」,標準寫法為「{std}」')


# 11. 年齡表與角色狀態
def snapshot_text():
    snap = sorted(glob.glob('狀態/*結束'))
    return read(f'{snap[-1]}/角色狀態.md') if snap else ''


def check_ages(vol_dir=None):
    snaps = sorted(glob.glob('狀態/*結束'))
    if vol_dir is None:
        vol_dir = '故事線/' + os.path.basename(snaps[-1])[:-2] if snaps else '故事線/序卷'
    p = f'{vol_dir}/年齡表.md'
    if not os.path.exists(p):
        return
    ages = {}
    for line in read(p).split('\n'):
        c = [x.strip() for x in line.strip('|').split('|')]
        if len(c) >= 3 and re.fullmatch(r'\d+', c[2]):
            ages[c[0]] = int(c[2])
    for line in snapshot_text().split('\n'):
        c = [x.strip() for x in line.strip('|').split('|')]
        if len(c) >= 5 and c[0] in ages:
            m = re.search(r'\d+', c[4])
            if m and int(m.group()) != ages[c[0]]:
                add('年齡', f'{c[0]} 狀態表 {c[4]} 與年齡表 {ages[c[0]]} 不一致')


# 12. 戰力基準人物表與狀態表
def check_baseline():
    state = {}
    for line in snapshot_text().split('\n'):
        c = [x.strip() for x in line.strip('|').split('|')]
        if len(c) >= 6 and re.fullmatch(r'L\d+', c[5]):
            state[c[0]] = c[5]
    skip = False
    for line in read('武學設定/總綱/戰力基準.md').split('\n'):
        if line.startswith('#'):
            skip = '序卷結束時點' in line  # 該段為起點值,進境見各卷成長紀錄
            continue
        c = [x.strip() for x in line.strip('|').split('|')]
        if not skip and len(c) >= 2 and re.fullmatch(r'L\d+', c[1]):
            keys = {c[0]}
            m = re.search(r'\((.*?)\)', c[0])
            if m:
                keys.add(m.group(1))
                keys.add(c[0].split('(')[0])
            for n, lv in state.items():
                if n in keys and lv != c[1]:
                    add('戰力', f'戰力基準 {c[0]} {c[1]} 與狀態表 {n} {lv} 不一致')



# 13. 章節大綱與事件描述的章節欄一致
def check_chapters_all():
    for v in ('序卷', '第一部', '第二部', '第三部'):
        if os.path.exists(f'故事線/{v}/事件描述.md'):
            check_chapters(f'故事線/{v}')


def check_chapters(vol_dir='故事線/序卷'):
    d = f'{vol_dir}/章節'
    if not os.path.isdir(d):
        return
    src = read(f'{vol_dir}/事件描述.md')
    ev_ch = {}
    for sec in re.split(r'\n(?=### )', src):
        m = re.match(r'### (\w+-\d+) ', sec)
        c = re.search(r'- \*\*章節\*\*:(.*)', sec)
        if m and c:
            ev_ch[m.group(1)] = c.group(1).strip().replace(' ', '')
    seen = {}
    for f in sorted(glob.glob(f'{d}/[0-9]*.md')):
        t = read(f)
        title = re.match(r'# (.*?) · ', t).group(1).replace(' ', '')
        m = re.search(r'- \*\*對應事件\*\*:(.*)', t)
        for eid in re.findall(r'\w+-\d+', m.group(1) if m else ''):
            seen[eid] = title
    for eid, ch in ev_ch.items():
        if seen.get(eid) != ch:
            add('章節', f'{eid} 事件描述章節為「{ch}」,章節大綱為「{seen.get(eid)}」')
    for eid in seen:
        if eid not in ev_ch:
            add('章節', f'章節大綱引用不存在的事件 {eid}')



# 14. 標籤詞表與節奏檢視
def check_tags(vol_dir='故事線/序卷'):
    import importlib.util
    t = read('設計規範/標籤表.md')
    sec_event = t.split('## 事件標籤')[1].split('## 感情線')[0]
    sec_love = t.split('## 感情線')[1].split('## 規劃步驟')[0]
    tags = set(re.findall(r'^\| (\S+) \| .*? \| (?:緩衝|推進|重) \|$', sec_event, re.M))
    states = set(re.findall(r'^\| (\S+) \| (?!意義).*\|$', sec_love, re.M)) - {'---'}
    spec = importlib.util.spec_from_file_location('標籤檢視', '工具/標籤檢視.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for r in mod.parse_timeline(vol_dir):
        for tg in [x for x in re.split(r'[、,]', r['事件標籤']) if x]:
            if tg not in tags:
                add('標籤', f"{r['事件 ID']} 使用未登錄的標籤「{tg}」")
        if r['感情線'] != '-':
            st = r['感情線'].split()[0]
            if st not in states:
                add('標籤', f"{r['事件 ID']} 使用未登錄的感情線狀態「{st}」")
            elif len(r['感情線'].split()) > 1:
                add('標籤', f"{r['事件 ID']} 感情線只填狀態詞,不加其他符號或文字")
    text, _ = mod.render(vol_dir)
    f = f'{vol_dir}/節奏檢視.md'
    if not os.path.exists(f) or read(f) != text:
        add('標籤', f'{f} 已過期,請執行 python3 工具/標籤檢視.py')



# 19. 第一部年齡表:與序卷銜接、與設定檔及時間線一致
def age_table(path):
    rows = {}
    for line in read(path).split('\n'):
        c = [x.strip() for x in line.strip('|').split('|')]
        if len(c) >= 3 and c[0] and c[0] not in ('角色', '---', '滿歲', '時點'):
            rows[c[0]] = c
    return rows


def label_months(label):
    s = label.replace('初遇後', '').strip()
    if '夜' in s and not re.search(r'\d', s):
        return 0.0
    m = 0.0
    for n, unit in re.findall(r'(\d+)\s*(年|個月|日)', s):
        m += int(n) * {'年': 12, '個月': 1, '日': 1 / 30}[unit]
    return m


def tl_months(v):
    """回傳該卷時間線所有事件起始月數(用於換算年齡與前後卷銜接)。"""
    out = []
    tl = f'故事線/{v}/時間線.md'
    if not os.path.exists(tl):
        return out
    for line in read(tl).split('\n'):
        c = [x.strip() for x in line.strip('|').split('|')]
        if len(c) > 5 and c[0].isdigit():
            out.append(label_months(c[2].split('–')[0]))
    return out


def check_vol_ages_all():
    for v, prev in (('第一部', '序卷'), ('第二部', '第一部'), ('第三部', '第二部')):
        check_vol_ages(v, prev)


def check_vol_ages(v='第一部', prev='序卷'):
    p = f'故事線/{v}/年齡表.md'
    if not os.path.exists(p):
        return
    cur = age_table(p)
    old = age_table(f'故事線/{prev}/年齡表.md')
    # 本卷起點相對初遇夜的整年數:第一部為 0;之後的卷起點晚於初遇夜,年齡以「起點年齡 + (滿年數 − 起點整年數)」換算
    ms = tl_months(v)
    off = int(min(ms) // 12 + 1e-9) if ms else 0
    pms = tl_months(prev)
    # 與前卷銜接:本卷起點 = 前卷結束(跨過增歲點則加 1;前卷為序卷時直接相等)
    bump = 0 if prev == '序卷' or not pms else off - int(max(pms) // 12 + 1e-9)
    for name, c in cur.items():
        if name in old and re.fullmatch(r'\d+', c[1]) and re.fullmatch(r'\d+', old[name][2]):
            if int(c[1]) != int(old[name][2]) + bump:
                add('年齡', f'{v}年齡表 {name} 起點 {c[1]} 與{prev}年齡表結束 {old[name][2]}(跨增歲點 +{bump})不一致')
    # 設定檔
    for name, c in cur.items():
        f = f'角色/主要角色/{name}/設定/{v}.md'
        if os.path.exists(f) and re.fullmatch(r'\d+', c[1]):
            m = re.search(r'\*\*(?:初始)?年齡\*\*:約?\s*(\d+)', read(f))
            if m and m.group(1) != c[1]:
                add('年齡', f'{f} 年齡 {m.group(1)} 與年齡表起點 {c[1]} 不一致')
    # 時間線:歲數 = 起點 + 滿年數 − 本卷起點整年數
    tl = f'故事線/{v}/時間線.md'
    if os.path.exists(tl) and '男主' in cur and re.fullmatch(r'\d+', cur['男主'][1]):
        base = int(cur['男主'][1]) - off
        head = None
        for line in read(tl).split('\n'):
            if not line.startswith('|'):
                continue
            c = [x.strip() for x in line.strip('|').split('|')]
            if c[0] == '序':
                head = c
            elif head and len(c) == len(head) and c[0].isdigit():
                r = dict(zip(head, c))
                parts = r['相對時間'].split('–')
                ages = []
                for part in parts:
                    a = base + int(label_months(part) // 12 + 1e-9)
                    if not ages or ages[-1] != a:
                        ages.append(a)
                exp = '–'.join(str(a) for a in ages)
                for who in ('男主', '女主'):
                    if r[who] != exp:
                        add('年齡', f"{v}時間線 {r['事件 ID']} {who}歲數 {r[who]},依年齡表應為 {exp}")


# 20. 凍結紀錄:時間線的事件 ID、相對時間、章節不得與凍結紀錄不一致
def check_freeze():
    for v in ('第一部', '第二部', '第三部'):
        fz, tl = f'故事線/{v}/凍結.md', f'故事線/{v}/時間線.md'
        if not (os.path.exists(fz) and os.path.exists(tl)):
            continue
        frozen = {}
        for line in read(fz).split('\n'):
            c = [x.strip() for x in line.strip('|').split('|')]
            if len(c) == 6 and re.fullmatch(r'P\d-\d+', c[0]):
                frozen[c[0]] = c
        head = None
        live = {}
        for line in read(tl).split('\n'):
            if not line.startswith('|'):
                continue
            c = [x.strip() for x in line.strip('|').split('|')]
            if c[0] == '序':
                head = c
            elif head and len(c) == len(head) and c[0].isdigit():
                r = dict(zip(head, c))
                live[r['事件 ID']] = r
        for eid, r in live.items():
            if eid not in frozen:
                add('凍結', f'{v} {eid} 不在凍結紀錄,請走變更傳播並更新 {fz}')
            elif frozen[eid][1] != r['相對時間'] or frozen[eid][2] != r['章節']:
                add('凍結', f"{v} {eid} 時間或章節已與凍結紀錄不同(凍結:{frozen[eid][1]}/{frozen[eid][2]};現在:{r['相對時間']}/{r['章節']})")
        for eid in frozen:
            if eid not in live:
                add('凍結', f'{v} {eid} 在凍結紀錄中,但時間線已無此事件(事件 ID 不得刪除或重編)')


# 21. 缺口掃描:已結案的卷,凍結紀錄的出場者都必須有檔案(或登記待建)
def check_gaps():
    import importlib.util
    spec = importlib.util.spec_from_file_location('缺口掃描', '工具/缺口掃描.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for v in ('第一部', '第二部', '第三部'):
        rp = f'故事線/{v}/缺口掃描.md'
        if not (os.path.exists(rp) and os.path.exists(f'故事線/{v}/凍結.md')):
            continue
        if '狀態:已結案' not in read(rp):
            continue
        uses, gaps = mod.scan(v)
        labels = {'角色': '缺角色資料夾', '角色設定': f'缺 設定/{v}.md', '勢力': '缺勢力檔', '場景': '缺場景建模且未登記待建'}
        for k, label in labels.items():
            for n, ev in gaps[k]:
                add('缺口', f'{v} {label}:{n}(首見 {ev[0]})')


# 22. 事件描述:與時間線逐項一致,出場者與場景與凍結紀錄一致
def check_event_desc():
    for v, pre in (('第一部', 'P1'), ('第二部', 'P2'), ('第三部', 'P3')):
        ed, tl, fz = (f'故事線/{v}/{x}.md' for x in ('事件描述', '時間線', '凍結'))
        if not (os.path.exists(ed) and os.path.exists(tl) and os.path.exists(fz)):
            continue
        live, head = {}, None
        for line in read(tl).split('\n'):
            if not line.startswith('|'):
                continue
            c = [x.strip() for x in line.strip('|').split('|')]
            if c[0] == '序':
                head = c
            elif head and len(c) == len(head) and c[0].isdigit():
                r = dict(zip(head, c))
                live[r['事件 ID']] = r
        frozen = {}
        for line in read(fz).split('\n'):
            c = [x.strip() for x in line.strip('|').split('|')]
            if len(c) == 6 and re.fullmatch(r'P\d-\d+', c[0]):
                frozen[c[0]] = c
        seen = set()
        for sec in re.split(r'\n(?=### )', read(ed)):
            m = re.match(rf'### ({pre}-\d+) (.*)', sec)
            if not m:
                continue
            eid, name = m.group(1), m.group(2).strip()
            seen.add(eid)
            if eid not in live:
                add('事件描述', f'{v} {eid} 不在時間線')
                continue
            r = live[eid]
            get = lambda k: (re.search(rf'- \*\*{k}\*\*:(.*)', sec) or [None, ''])[1].strip()
            for k, tk in (('序號', '序'), ('時間', '相對時間'), ('章節', '章節')):
                if get(k) != r[tk]:
                    add('事件描述', f'{v} {eid} {k}「{get(k)}」與時間線「{r[tk]}」不一致')
            if name != r['事件名稱']:
                add('事件描述', f'{v} {eid} 標題與時間線事件名稱不一致')
            if not get('描述') or len(get('描述')) > 120:
                add('事件描述', f'{v} {eid} 描述缺漏或超過 120 字(應為一至兩句)')
            cast = get('出場角色')
            roles = set(re.findall(r'\[([^\]]+)\]\(\.\./\.\./角色/', cast))
            orgs = set(re.findall(r'\(\.\./\.\./勢力/([^)]+)\.md\)', cast))
            sc = get('場景')
            m2 = re.search(r'場景設定/([^/]+)/建模描述', sc) or re.search(r'待建:(.+)', sc)
            scene = m2.group(1).strip() if m2 else ''
            z = frozen.get(eid)
            if not z:
                add('事件描述', f'{v} {eid} 不在凍結紀錄')
                continue
            fr = {x for x in z[3].split('、') if x}
            fo = {x for x in z[4].split('、') if x and x != '—'}
            if roles != fr:
                add('事件描述', f'{v} {eid} 出場角色與凍結紀錄不一致(差異:{sorted(roles ^ fr)})')
            if orgs != fo:
                add('事件描述', f'{v} {eid} 出場勢力與凍結紀錄不一致(差異:{sorted(orgs ^ fo)})')
            if scene != z[5]:
                add('事件描述', f'{v} {eid} 場景「{scene}」與凍結紀錄「{z[5]}」不一致')
        for eid in live:
            if eid not in seen:
                add('事件描述', f'{v} {eid} 在時間線但沒有事件描述')


# 24. 紀錄一致性:個性轉變的歲數、武學起點戰力
def check_record_consistency(v):
    ap = f'故事線/{v}/年齡表.md'
    tl = f'故事線/{v}/時間線.md'
    if not (os.path.exists(ap) and os.path.exists(tl)):
        return
    ages = age_table(ap)
    when, head = {}, None
    for line in read(tl).split('\n'):
        if not line.startswith('|'):
            continue
        c = [x.strip() for x in line.strip('|').split('|')]
        if c[0] == '序':
            head = c
        elif head and len(c) == len(head) and c[0].isdigit():
            r = dict(zip(head, c))
            when[r['事件 ID']] = label_months(r['相對時間'].split('–')[0])
    snap = ''
    prev = {'第一部': '序卷', '第二部': '第一部', '第三部': '第二部'}.get(v)
    if prev and os.path.exists(f'狀態/{prev}結束/角色狀態.md'):
        snap = read(f'狀態/{prev}結束/角色狀態.md')  # 男女主的起點戰力取上一卷結束時點
    for n, r in roots().items():
        # 個性轉變:時間欄的「(N 歲)」須等於年齡表起點加上滿年數
        pf = f'{r}/成長/個性/{v}.md'
        if os.path.exists(pf) and n in ages and re.fullmatch(r'\d+', ages[n][1]):
            for blk in re.split(r'\n(?=## 轉變)', read(pf)):
                e = re.search(r'\*\*觸發事件\*\*:(\S+)', blk)
                a = re.search(r'\*\*時間\*\*:.*?\((\d+) 歲\)', blk)
                if e and a and e.group(1) in when:
                    exp = int(ages[n][1]) + int(when[e.group(1)] // 12 + 1e-9) - int(min(when.values()) // 12 + 1e-9)
                    if int(a.group(1)) != exp:
                        add('個性', f'{pf} {e.group(1)} 的歲數 {a.group(1)},依年齡表應為 {exp}')
        # 武學:第一個時間段的戰力須等於設定檔(男女主則等於上一卷結束的狀態表)
        wf = f'{r}/成長/武學/{v}.md'
        if os.path.exists(wf):
            m = re.search(r'\*\*戰力\*\*:L(\d+)', read(wf))
            base = None
            sf = f'{r}/設定/{v}.md'
            if os.path.exists(sf):
                b = re.search(r'\*\*戰力\*\*:L(\d+)', read(sf))
                base = b.group(1) if b else None
            elif n in ('男主', '女主'):
                b = re.search(rf'^\| {n} \| [^|]+\| [^|]+\| [^|]+\| [^|]+\| L(\d+)', snap, re.M)
                base = b.group(1) if b else None
            # 首次出場較晚的少年可能已有進境,容許 0 至 +3;低於起點或超過 +3 視為不一致
            if m and base and not (int(base) <= int(m.group(1)) <= int(base) + 3):
                add('戰力', f'{wf} 起點戰力 L{m.group(1)} 與設定/狀態表 L{base} 不一致(容許 +0 至 +3)')


# 23. 階段 D:紀錄對照標「狀態:已結案」後,啟用事件覆蓋、感情對稱、個性轉變與佔位符檢查
def check_stage_d():
    for v, pre in (('第一部', 'P1'), ('第二部', 'P2'), ('第三部', 'P3')):
        rp = f'故事線/{v}/紀錄對照.md'
        if not (os.path.exists(rp) and '狀態:已結案' in read(rp)):
            continue
        check_events(volume=v, volume_dir=f'故事線/{v}', prefix=pre)
        check_symmetry(v)
        check_personality(f'故事線/{v}', v, pre)
        for f in glob.glob(f'角色/**/成長/**/{v}.md', recursive=True):
            if '(待填)' in read(f):
                add('紀錄', f'{f} 仍有「(待填)」')
        check_record_consistency(v)


def check_tags_all():
    for v in ('序卷', '第一部', '第二部', '第三部'):
        d = f'故事線/{v}'
        # 標籤尚未填寫(含「待填」)的卷視為仍在 A4,不檢查
        if os.path.exists(f'{d}/時間線.md') and '待填' not in read(f'{d}/時間線.md'):
            check_tags(d)


# 15. 個性轉變記錄
def check_personality(vol_dir='故事線/序卷', volume='序卷', prefix='PRO'):
    ev = events(vol_dir, prefix)
    rs = roots()
    for n, r in rs.items():
        f = f'{r}/成長/個性/{volume}.md'
        if not os.path.exists(f):
            continue
        t = read(f)
        for m in re.finditer(r'- \*\*觸發事件\*\*:(\S+)', t):
            eid = m.group(1)
            if eid not in ev:
                add('個性', f'{f} 觸發事件 {eid} 不存在')
            elif n not in ev[eid]:
                add('個性', f'{f} 觸發事件 {eid} 的出場者不含「{n}」')
        if '## 卷末個性摘要' not in t:
            add('個性', f'{f} 缺少「卷末個性摘要」')
    # 狀態表必須有「當前個性」欄
    snap = sorted(glob.glob('狀態/*結束'))
    if snap and '當前個性' not in read(f'{snap[-1]}/角色狀態.md'):
        add('個性', '角色狀態缺少「當前個性」欄')



# 16. 卷完成度:必備檔案齊全
def check_completeness():
    vols = {'序卷': '序卷', '第一部': '第一部', '第二部': '第二部', '第三部': '第三部'}
    for v in vols:
        d = f'故事線/{v}'
        if not os.path.exists(f'{d}/事件描述.md'):
            continue  # 尚未開發的卷不檢查
        need = [f'{d}/{x}' for x in ('大綱.md', '時間線.md', '節奏檢視.md', '吸引力分析.md', '年齡表.md', '章節/README.md')]
        # 卷末快照屬階段 F:該卷已開始收尾(有 狀態/{卷}結束/ 資料夾)才要求齊全
        if os.path.isdir(f'狀態/{v}結束') or v == '序卷':
            need += [f'狀態/{v}結束/{x}' for x in ('角色狀態.md', '地區與國家狀態.md', '勢力狀態.md', '世界狀態.md')]
            need += ['狀態/秘密知情矩陣.md', '狀態/伏筆登記簿.md']
        for f in need:
            if not os.path.exists(f):
                add('完成度', f'{v} 缺少 {f}')


# 17. 卷大綱與宏觀大綱的章級線別一致
def chapter_tags(path):
    tags = {}
    for line in read(path).split('\n'):
        m = re.match(r'- 第 (\d+)(?:–(\d+))? 章【(\w+)】', line)
        if m:
            a = int(m.group(1))
            b = int(m.group(2) or a)
            for n in range(a, b + 1):
                tags[n] = m.group(3)
    return tags


def check_outline_tags():
    for v, macro_path in (('第一部', '故事大綱/第一部_少年遊.md'), ('第二部', '故事大綱/第二部_離亂行.md'),
                          ('第三部', '故事大綱/第三部_補天錄.md')):
        p = f'故事線/{v}/大綱.md'
        if not os.path.exists(p):
            continue
        macro, vol = chapter_tags(macro_path), chapter_tags(p)
        for n in sorted(set(macro) | set(vol)):
            if macro.get(n) != vol.get(n):
                add('大綱', f'{v} 第 {n} 章線別:宏觀大綱為「{macro.get(n)}」,卷大綱為「{vol.get(n)}」')


# 18. 時間線骨架:事件 ID 前綴與連號、章節覆蓋卷大綱的每一章
def check_timeline_skeleton():
    prefixes = {'第一部': 'P1', '第二部': 'P2', '第三部': 'P3'}
    for v, pre in prefixes.items():
        tl, outline = f'故事線/{v}/時間線.md', f'故事線/{v}/大綱.md'
        if not (os.path.exists(tl) and os.path.exists(outline)):
            continue
        rows = []
        head = None
        for line in read(tl).split('\n'):
            if not line.startswith('|'):
                continue
            c = [x.strip() for x in line.strip('|').split('|')]
            if c[0] == '序':
                head = c
            elif head and len(c) == len(head) and c[0].isdigit():
                rows.append(dict(zip(head, c)))
        nums = []
        for r in rows:
            m = re.fullmatch(rf'{pre}-(\d+)', r['事件 ID'])
            if not m:
                add('時間線', f"{v} 事件 ID「{r['事件 ID']}」不符合前綴 {pre}-")
            else:
                nums.append(int(m.group(1)))
        if sorted(nums) != list(range(1, len(nums) + 1)):
            add('時間線', f'{v} 事件 ID 不連號或重複')
        covered = set()
        for r in rows:
            m = re.fullmatch(r'第 (\d+) 章', r['章節'])
            if m:
                covered.add(int(m.group(1)))
            else:
                add('時間線', f"{v} {r['事件 ID']} 章節欄「{r['章節']}」格式不符")
        for n in chapter_tags(outline):
            if n not in covered:
                add('時間線', f'{v} 第 {n} 章沒有任何事件')
        for n in covered - set(chapter_tags(outline)):
            add('時間線', f'{v} 時間線引用卷大綱沒有的第 {n} 章')


# 28. 招式錄:事件 ID、出場者、章節區間與凍結紀錄一致;套路錄的「已出場」須有招式錄為證
def check_move_records():
    seen = set()
    for v, pre in (('第一部', 'P1'), ('第二部', 'P2'), ('第三部', 'P3')):
        mp, fz = f'武學設定/招式/{v}招式錄.md', f'故事線/{v}/凍結.md'
        if not os.path.exists(mp):
            continue
        if not os.path.exists(fz):
            add('招式錄', f'{mp} 沒有對應的凍結紀錄')
            continue
        frozen = {}
        for line in read(fz).split('\n'):
            c = [x.strip() for x in line.strip('|').split('|')]
            if len(c) == 6 and re.fullmatch(r'P\d-\d+', c[0]):
                frozen[c[0]] = c
        lo = hi = None
        for line in read(mp).split('\n'):
            m = re.match(r'## .*\(第 (\d+)[–-](\d+) 章\)', line)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                continue
            c = [x.strip() for x in line.strip('|').split('|')]
            if not line.startswith('|') or not re.fullmatch(r'P\d-\d+', c[0]):
                continue
            eid = c[0]
            seen.add(eid)
            z = frozen.get(eid)
            if not z:
                add('招式錄', f'{mp} {eid} 不在凍結紀錄')
                continue
            roster = {x for x in z[3].split('、') + z[4].split('、') if x and x != '—'}
            for name in [x for x in c[1].split('、') if x]:
                if name not in roster:
                    add('招式錄', f'{mp} {eid} 出場者「{name}」不在凍結紀錄的出場名單')
            m2 = re.fullmatch(r'第 (\d+) 章', z[2])
            if lo is None or not m2 or not lo <= int(m2.group(1)) <= hi:
                add('招式錄', f'{mp} {eid} 的章節「{z[2]}」不在所屬小節的章節區間')
            if len(c) != 6 or not all(c):
                add('招式錄', f'{mp} {eid} 欄位不足或有空欄')
    sp = '武學設定/招式/套路錄.md'
    if os.path.exists(sp):
        for ids in re.findall(r'已出場\(([^)]*)\)', read(sp)):
            for eid in re.findall(r'P\d-\d+', ids):
                if eid not in seen:
                    add('招式錄', f'{sp} 標「已出場」的 {eid} 沒有對應的招式錄')

# 29. 單次出場:本卷只出現在一個事件的角色(男女主除外)不建該卷的記憶、武學、個性、感情紀錄
def check_single_appearance():
    rs = roots()
    for v, pre in (('序卷', 'PRO'), ('第一部', 'P1'), ('第二部', 'P2'), ('第三部', 'P3')):
        d = f'故事線/{v}'
        if not os.path.exists(f'{d}/事件描述.md'):
            continue
        cnt = {}
        for names in events(d, pre).values():
            for n in names:
                cnt[n] = cnt.get(n, 0) + 1
        for n, k in cnt.items():
            if k != 1 or n in ('男主', '女主') or n not in rs:
                continue
            for pat in (f'{rs[n]}/成長/記憶/{v}.md', f'{rs[n]}/成長/武學/{v}.md', f'{rs[n]}/成長/個性/{v}.md',
                        f'{rs[n]}/成長/感情/*/{v}.md'):
                for f in glob.glob(pat):
                    add('單次出場', f'{n} 在{v}只出現一次,不需要 {f}')

# 30. 出場順序:新名字不能太密,隔太久再出現要有回頭提示;出場順序.md 須為最新
def check_appearance_order():
    import importlib.util
    spec = importlib.util.spec_from_file_location('出場順序', '工具/出場順序.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for v in ('第一部', '第二部', '第三部'):
        d = f'故事線/{v}'
        f = f'{d}/出場順序.md'
        if not (os.path.exists(f) and (os.path.exists(f'{d}/事件描述.md') or os.path.exists(f'{d}/凍結.md')) and os.path.exists(f'{d}/時間線.md')):
            continue
        for x in mod.problems(d):
            add('出場順序', f'{v} {x}')
        if read(f) != mod.render(d):
            add('出場順序', f'{f} 已過期,請執行 python3 工具/出場順序.py {d}')

for fn in (check_links, check_symmetry, check_power_cap, check_events, check_ratio, check_state_power,
           check_ids, check_terms, check_ages, check_baseline, check_chapters_all, check_tags_all, check_personality, check_completeness, check_outline_tags, check_timeline_skeleton, check_vol_ages_all, check_freeze, check_gaps, check_event_desc, check_stage_d, check_move_records, check_single_appearance, check_appearance_order):
    fn()

if problems:
    print(f'發現 {len(problems)} 個問題:')
    for p in problems:
        print(' ', p)
    sys.exit(1)
print('全部檢查通過')
