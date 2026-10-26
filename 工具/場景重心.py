#!/usr/bin/env python3
"""場景重心(DEC-101):演出事件的舞台分布。

使用者要求故事重心放在江湖、武林與宗門,減少宮城與塞外。本工具依事件描述的「場景」欄,
把各部的演出事件(不含背景與提及)分到五類,並檢查「宮城朝堂 + 塞外」是否在上限內。

  python3 工具/場景重心.py            # 印出分布
  python3 工具/場景重心.py --strict   # 超過上限時以結束碼 1 結束

分類以場景名稱為準,設定見 設計規範/場景重心.md;改分類或上限時兩處同步。
這是舞台的量測,不是品質判斷:一個事件發生在宮城,不代表它是朝堂戲(朝堂戲另見 朝堂分類.md)。
"""
import glob
import re
import sys
from collections import Counter

PALACE = {'東宮與皇城', '長寧朝堂與坊市', '臨江行在', '祭天壇'}
BEYOND = {'玄朔大營', '草原邊緣', '河西走廊', '沉沙古城', '月牙泉宮'}
FRONT = {'雁回關', '幽州節度使府', '潼關', '洛北孤城', '河東', '高承嗣長寧行轅',
         '江左營地', '長江江面', '洛水', '斷碑村'}
LIMIT = {'第一部': 25.0, '第二部': 30.0, '第三部': 25.0}  # 宮城朝堂 + 塞外 的上限(%)
VOLS = ['序卷', '第一部', '第二部', '第三部']


def kind(scene):
    if scene in PALACE:
        return '宮城朝堂'
    if scene in BEYOND:
        return '塞外'
    if scene in FRONT:
        return '邊關軍旅'
    return '江湖市井宗門'


def load(vol):
    text = open(f'故事線/{vol}/事件描述.md', encoding='utf-8').read()
    rows = []
    for blk in re.split(r'^### ', text, flags=re.M)[1:]:
        head = blk.split('\n')[0]
        m = re.match(r'((?:P[123]|PRO)-\d+)', head)
        ch = re.search(r'\*\*章節\*\*:(.*)', blk)
        sc = re.search(r'\*\*場景\*\*:\[([^\]]+)\]', blk)
        if not (m and ch and sc):
            continue
        chv = ch.group(1).strip()
        if chv == '背景' or '提及' in chv:
            continue
        rows.append((m.group(1), sc.group(1)))
    return rows


def main():
    strict = '--strict' in sys.argv
    order = ['宮城朝堂', '塞外', '邊關軍旅', '江湖市井宗門']
    print('| 卷 | 演出事件 | ' + ' | '.join(order) + ' | 宮城朝堂+塞外 | 上限 |')
    print('|---|---|' + '---|' * (len(order) + 2))
    bad = []
    for vol in VOLS:
        rows = load(vol)
        n = len(rows)
        c = Counter(kind(s) for _, s in rows)
        both = c['宮城朝堂'] + c['塞外']
        pct = both * 100 / n
        lim = LIMIT.get(vol)
        mark = ''
        if lim is not None:
            mark = f'{lim:.0f}%'
            if pct > lim:
                bad.append(f'{vol} 宮城朝堂+塞外 {pct:.1f}% 超過上限 {lim:.0f}%')
        cells = ' | '.join(f'{c[k]}({c[k] * 100 / n:.0f}%)' for k in order)
        print(f'| {vol} | {n} | {cells} | {both}({pct:.1f}%) | {mark or "—"} |')
    for b in bad:
        print('✗', b)
    if strict and bad:
        sys.exit(1)


if __name__ == '__main__':
    main()
