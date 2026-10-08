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


for fn in (check_links, check_symmetry, check_power_cap, check_events, check_ratio, check_state_power):
    fn()

if problems:
    print(f'發現 {len(problems)} 個問題:')
    for p in problems:
        print(' ', p)
    sys.exit(1)
print('全部檢查通過')
