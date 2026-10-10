#!/usr/bin/env python3
"""由時間線產生節奏檢視。用法:python3 工具/標籤檢視.py [卷資料夾,預設 故事線/序卷]
輸出兩個視角:事件標籤節奏、男女主感情線弧線,並寫入 {卷資料夾}/節奏檢視.md。"""
import os, re, sys

HEAVY = {'揭露', '驚魂', '悲劇', '死亡', '戰爭'}
BUFFER = {'敘事', '傳說', '設定', '日常', '成長', '溫情', '幽默', '相遇'}


def read(p):
    with open(p, encoding='utf8') as f:
        return f.read()


def parse_timeline(vol_dir):
    rows = []
    head = None
    for line in read(f'{vol_dir}/時間線.md').split('\n'):
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if cells[0] == '序':
            head = cells
            continue
        if head and len(cells) == len(head) and cells[0].isdigit():
            rows.append(dict(zip(head, cells)))
    return rows


def chapter_index(label):
    m = re.search(r'\d+', label)
    return int(m.group()) if m else 99


def render(vol_dir):
    all_rows = parse_timeline(vol_dir)
    name = os.path.basename(vol_dir)
    # 章節欄為「背景」或「第 N 章(提及)」的事件不在正文演出,不計入閱讀節奏(DEC-073),另表列出
    rows = [r for r in all_rows if '背景' not in r['章節'] and '提及' not in r['章節']]
    offstage = [r for r in all_rows if r not in rows]
    rows.sort(key=lambda r: (chapter_index(r['章節']), int(r['序'])))
    out = [f'# {name} 節奏檢視', '',
           '> 由 `工具/標籤檢視.py` 依時間線產生,請勿手動修改。順序為**閱讀順序**(依章節,再依事件序)。',
           '> 標籤詞表與規劃步驟見 [標籤表](../../設計規範/標籤表.md)。', '']
    # 視角一:事件標籤
    out += ['## 視角一:事件標籤節奏', '', '| 章 | 事件(標籤) | 重 | 推進 | 緩衝 |', '|---|---|---|---|---|']
    chapters = {}
    for r in rows:
        chapters.setdefault(r['章節'], []).append(r)
    total = {'重': 0, '緩衝': 0, '推進': 0}
    warns = []
    streak = 0
    start = None
    last = None

    def close_streak():
        nonlocal streak, start
        if streak > 2:
            warns.append(f'{start} 至 {last} 連續 {streak} 個「重」事件,缺緩衝')
        streak = 0
        start = None
    for ch, rs in chapters.items():
        seq = []
        cnt = {'重': 0, '緩衝': 0, '推進': 0}
        for r in rs:
            tags = [t for t in re.split(r'[、,]', r['事件標籤']) if t]
            seq.append(f"{r['事件 ID']}({'、'.join(tags)})")
            kinds = set()
            for t in tags:
                k = '重' if t in HEAVY else '緩衝' if t in BUFFER else '推進'
                kinds.add(k)
            for k in kinds:
                cnt[k] += 1
                total[k] += 1
            if '重' in kinds and '緩衝' not in kinds:
                if streak == 0:
                    start = r['事件 ID']
                streak += 1
                last = r['事件 ID']
            elif '緩衝' in kinds:
                close_streak()
        out.append(f"| {ch} | {'<br>'.join(seq)} | {cnt['重']} | {cnt['推進']} | {cnt['緩衝']} |")
    close_streak()
    n = len(rows)
    out += ['', f"{'演出事件' if offstage else '全卷'} {n} 個{'' if offstage else '事件'}:重 {total['重']}、推進 {total['推進']}、緩衝 {total['緩衝']}"
            f"(緩衝占比約 {total['緩衝'] / n * 100:.0f}%,建議不低於 30%)。", '']
    if total['緩衝'] / n < 0.3:
        warns.append('緩衝類事件占比低於 30%')
    # 視角二:感情線
    out += ['## 視角二:男女主感情線弧線', '']
    seq = [(r['事件 ID'], r['感情線'], r['事件名稱']) for r in rows if r['感情線'] != '-']
    if not seq:
        out.append('本卷尚無感情線事件。')
    else:
        out += ['| 事件 | 感情線 | 事件名稱 |', '|---|---|---|']
        for eid, love, nm in seq:
            out.append(f'| {eid} | {love} | {nm} |')
        states = [s.split()[0] for _, s, _ in seq]
        out += ['', '弧線:' + ' → '.join(states)]
        for i, s in enumerate(states):
            if s in ('爭執', '分離') and not any(x in ('和好', '理解', '重逢', '情定') for x in states[i + 1:]):
                warns.append(f'感情線「{s}」之後本卷尚無收束(和好/理解/重逢/情定)')
    out.append('')
    if offstage:
        out += ['## 口述與背景事件(不計入閱讀節奏)', '', '| 去向 | 事件(標籤) |', '|---|---|']
        groups = {}
        for r in offstage:
            groups.setdefault(r['章節'], []).append(f"{r['事件 ID']}({r['事件標籤']})")
        for g, v in groups.items():
            out.append(f"| {g} | {'、'.join(v)} |")
        out.append('')
    out += ['## 提醒', '']
    out += [f'- {w}' for w in warns] or ['- 無']
    out.append('')
    return '\n'.join(out), warns


if __name__ == '__main__':
    vol = sys.argv[1] if len(sys.argv) > 1 else '故事線/序卷'
    text, warns = render(vol)
    with open(f'{vol}/節奏檢視.md', 'w', encoding='utf8') as f:
        f.write(text)
    print(text)
