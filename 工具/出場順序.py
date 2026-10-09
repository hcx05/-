#!/usr/bin/env python3
"""依事件描述與時間線,產生各卷的「出場順序」檢視,並檢查角色是否出得太密或隔太久。

用法:python3 工具/出場順序.py 故事線/第一部
閱讀順序 = 依章節,再依事件序。「新登場」不含男女主,也不含前面各卷已出場的角色。

規則(讀者負擔護欄):
  1. 單一事件(場景)首次登場的新名字不超過 2 位。
  2. 單章首次登場的新名字不超過 4 位。
  3. 同一角色相隔 12 章以上再出現,中間章節的「群像補充」須有一條「回頭提示」提到他(讓讀者想起來)。
"""
import re, os, sys, glob, collections

MAX_EVENT, MAX_CHAPTER, GAP = 2, 4, 12
LEADS = ('男主', '女主')
VOLS = ['序卷', '第一部', '第二部', '第三部']


def read(p):
    return open(p, encoding='utf-8').read()


def casts(vol):
    p = f'故事線/{vol}/事件描述.md'
    out = {}
    if not os.path.exists(p):
        return out
    for m in re.finditer(r'### ([A-Z0-9]+-\d+) [^\n]+\n(.*?)(?=\n### |\Z)', read(p), re.S):
        c = re.search(r'- \*\*出場角色\*\*:(.*)', m.group(2))
        names = [n for n, path in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', c.group(1) if c else '') if '角色/' in path]
        out[m.group(1)] = ['懷虛子' if n.startswith('懷虛子') else n for n in names]
    return out


def timeline(vol):
    rows = {}
    for l in read(f'故事線/{vol}/時間線.md').split('\n'):
        c = [x.strip() for x in l.strip('|').split('|')]
        if len(c) > 8 and re.fullmatch(r'[A-Z0-9]+-\d+', c[1]) and c[0].isdigit():
            m = re.search(r'\d+', c[8])
            if m:
                rows[c[1]] = (int(c[0]), int(m.group()), c[5])
    return rows


def blurb(name, vol):
    for v in (vol, *reversed(VOLS)):
        for base in ('角色/主要角色/', '角色/'):
            p = f'{base}{name}/設定/{v}.md'
            if os.path.exists(p):
                t = read(p)
                i = re.search(r'\*\*身份\*\*:(.*)', t)
                l = re.search(r'\*\*外表\*\*:(.*)', t)
                return (i.group(1).strip() if i else '') + ('；' + l.group(1).strip()[:14] if l else '')
    return ''


def analyze(vol_dir):
    vol = os.path.basename(vol_dir.rstrip('/'))
    tl, cast = timeline(vol), casts(vol)
    known = set(LEADS)
    for v in VOLS[:VOLS.index(vol)]:
        for names in casts(v).values():
            known |= set(names)
    order = sorted((e for e in tl if e in cast), key=lambda e: (tl[e][1], tl[e][0]))
    seen = set(known)
    per_ev, per_ch, app = {}, collections.OrderedDict(), collections.defaultdict(list)
    for e in order:
        new = []
        for n in cast[e]:
            if n not in seen:
                new.append(n)
                seen.add(n)
        per_ev[e] = new
        per_ch.setdefault(tl[e][1], []).extend(new)
        for n in cast[e]:
            if n not in LEADS:
                app[n].append(tl[e][1])
    return vol, tl, cast, order, per_ev, per_ch, app


def reminders(vol_dir):
    out = collections.defaultdict(set)
    for f in glob.glob(f'{vol_dir}/章節/[0-9]*.md'):
        n = int(os.path.basename(f).split('_')[0])
        for line in read(f).split('\n'):
            if '回頭提示' in line:
                out[n].add(line)
    return out


def problems(vol_dir):
    vol, tl, cast, order, per_ev, per_ch, app = analyze(vol_dir)
    out = []
    for e, new in per_ev.items():
        if len(new) > MAX_EVENT:
            out.append(f'{e}(第 {tl[e][1]} 章)首次登場 {len(new)} 位新名字:{"、".join(new)}(上限 {MAX_EVENT})')
    for ch, new in per_ch.items():
        if len(new) > MAX_CHAPTER:
            out.append(f'第 {ch} 章首次登場 {len(new)} 位新名字:{"、".join(new)}(上限 {MAX_CHAPTER})')
    rem = reminders(vol_dir)
    for n, chs in app.items():
        cs = sorted(set(chs))
        for a, b in zip(cs, cs[1:]):
            if b - a >= GAP and not any(n in line for c in range(a + 1, b) for line in rem.get(c, ())):
                out.append(f'{n} 在第 {a} 章後相隔到第 {b} 章才再出現,中間章節沒有「回頭提示」')
    return out


def render(vol_dir):
    vol, tl, cast, order, per_ev, per_ch, app = analyze(vol_dir)
    L = [f'# {vol} 出場順序', '',
         '> 由 `工具/出場順序.py` 依事件描述與時間線產生,請勿手動修改。順序為**閱讀順序**(依章節,再依事件序)。',
         f'> 護欄:單一事件首次登場的新名字 ≤ {MAX_EVENT};單章 ≤ {MAX_CHAPTER};相隔 {GAP} 章以上再出現者,中間章節須有「回頭提示」。「新登場」不含男女主與前面各卷已出場的角色。', '',
         '## 一、逐章新登場', '', '| 章 | 新登場數 | 累計 | 新登場(身份;辨識點) |', '|---|---|---|---|']
    tot = 0
    for ch, new in per_ch.items():
        tot += len(new)
        L.append(f'| 第 {ch} 章 | {len(new)} | {tot} | ' + ('<br>'.join(f'{n}({blurb(n, vol)})' for n in new) if new else '—') + ' |')
    L += ['', f'本卷新登場共 {tot} 位(不含男女主與前卷已出場者)。', '', '## 二、各章首次登場最密的事件', '', '| 事件 | 章 | 事件名稱 | 新名字 |', '|---|---|---|---|']
    dense = sorted(((e, new) for e, new in per_ev.items() if len(new) >= 2), key=lambda x: (tl[x[0]][1], tl[x[0]][0]))
    for e, new in dense:
        L.append(f'| {e} | 第 {tl[e][1]} 章 | {tl[e][2]} | {"、".join(new)} |')
    if not dense:
        L.append('| — | — | — | — |')
    L += ['', f'## 三、相隔 {GAP} 章以上再出現的角色', '', '| 角色 | 前次 | 再出現 | 回頭提示 |', '|---|---|---|---|']
    rem = reminders(vol_dir)
    rows = []
    for n, chs in app.items():
        cs = sorted(set(chs))
        for a, b in zip(cs, cs[1:]):
            if b - a >= GAP:
                hit = [c for c in range(a + 1, b) if any(n in line for line in rem.get(c, ()))]
                rows.append((a, n, b, f'第 {"、".join(map(str, hit))} 章' if hit else '**缺**'))
    for a, n, b, h in sorted(rows):
        L.append(f'| {n} | 第 {a} 章 | 第 {b} 章 | {h} |')
    if not rows:
        L.append('| — | — | — | — |')
    pr = problems(vol_dir)
    L += ['', '## 四、檢查結果', '']
    L += [f'- {x}' for x in pr] if pr else ['全部符合護欄。']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    vd = sys.argv[1] if len(sys.argv) > 1 else '故事線/第一部'
    text = render(vd)
    open(f'{vd}/出場順序.md', 'w', encoding='utf-8').write(text)
    print(text)
