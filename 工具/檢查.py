#!/usr/bin/env python3
"""專案一致性檢查。用法:python3 工具/檢查.py(於專案根目錄執行)。有任何問題則結束碼為 1。"""
import glob, os, re, sys, urllib.parse

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
    for a, b in sorted(pairs):
        if b in rs and (b, a) not in pairs:
            add('感情對稱', f'{a}→{b} 有,但 {b}→{a} 沒有')


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
            who, dead = m.group(1), int(m.group(2).split('-')[1])
            for eid, names in ev.items():
                if who in names and int(eid.split('-')[1]) > dead:
                    add('已故', f'{who} 於 {eid} 出場,晚於死亡事件 {m.group(2)}')
    # 伏筆登記簿事件存在
    tp = '狀態/伏筆登記簿.md'
    if os.path.exists(tp):
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


# 8. 角色狀態 L 與設定一致
def check_state_power():
    snap = sorted(glob.glob('狀態/*結束'))
    if not snap:
        return
    for line in read(f'{snap[-1]}/角色狀態.md').split('\n'):
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) < 6 or not cells[5].startswith('L'):
            continue
        name, lv = cells[0], cells[5]
        p = f'角色/主要角色/{name}/設定/第一部.md'
        if os.path.exists(p):
            m = re.search(r'\*\*戰力\*\*:(L\d+)', read(p))
            if m and m.group(1) != lv:
                add('戰力', f'{name} 狀態表 {lv} 與第一部設定 {m.group(1)} 不一致')


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


def check_ages(vol_dir='故事線/序卷'):
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
    for line in read('武學設定/總綱/戰力基準.md').split('\n'):
        c = [x.strip() for x in line.strip('|').split('|')]
        if len(c) >= 2 and re.fullmatch(r'L\d+', c[1]):
            keys = {c[0]}
            m = re.search(r'\((.*?)\)', c[0])
            if m:
                keys.add(m.group(1))
                keys.add(c[0].split('(')[0])
            for n, lv in state.items():
                if n in keys and lv != c[1]:
                    add('戰力', f'戰力基準 {c[0]} {c[1]} 與狀態表 {n} {lv} 不一致')


for fn in (check_links, check_symmetry, check_power_cap, check_events, check_ratio, check_state_power,
           check_ids, check_terms, check_ages, check_baseline):
    fn()

if problems:
    print(f'發現 {len(problems)} 個問題:')
    for p in problems:
        print(' ', p)
    sys.exit(1)
print('全部檢查通過')
