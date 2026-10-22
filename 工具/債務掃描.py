#!/usr/bin/env python3
"""債務掃描:列出會讓模型寫不穩的既有缺口,供排優先序。唯讀,不改任何檔。

用法:
    python3 工具/債務掃描.py              # 全部項目
    python3 工具/債務掃描.py --接下來 10   # 場景待建只看「接下來 N 個未完成章」會用到的

項目:
  A 未決標記   含「待定 / 待填 / 暫定 / 待確認」的檔案(多半是設定留白,模型會自行發明)
  B 場景待建   場景設定 README 登記為待建、卻會在後續章節用到的場景(依其引用的事件換算章號)
  C 大綱補丁   章節大綱裡後加的「增補/改版/對齊」段落(補丁與本文並存,應擇機併入本文)
  D 待回補     帳本中尚未回補到設定檔的新增事實
  E 暫定名     男女主 README 的暫定名(正式名未定會逼模型自己選)
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

MARK = re.compile(r'待定|待填|暫定|待確認')
SKIP_PREFIX = ('工具/', '手冊/', '正文/待決/', '重構計畫.md', '開發標準.md', '開發順序.md', '.github/', '索引/', '.claude/',
               '正文/帳本/補充登記_舊.md', '設計規範/術語表.md', 'AGENTS.md', 'CLAUDE.md')


def acknowledged():
    """設計規範/債務確認.md 第一節的路徑前綴;第二節的場景名稱。"""
    pref, scenes = [], []
    pth = '設計規範/債務確認.md'
    if not L.exists(pth):
        return pref, scenes
    for head, cols, rows in L.md_tables(L.read(pth)):
        if cols and cols[0] == '路徑前綴':
            for r in rows:
                pref += re.findall(r'`([^`]+)`', r[0])
        elif cols and cols[0] == '場景':
            scenes += [r[0].strip() for r in rows]
    return pref, scenes


def section_a():
    print('## A. 未決標記(待定 / 待填 / 暫定 / 待確認)\n')
    ack, _ = acknowledged()
    rows = []
    for root, dirs, files in os.walk(L.ROOT):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fn in files:
            if not fn.endswith('.md'):
                continue
            full = os.path.join(root, fn)
            r = L.rel(full)
            if r.startswith(SKIP_PREFIX) or any(r.startswith(a) for a in ack):
                continue
            hits = [ln.strip() for ln in L.read(full).split('\n') if MARK.search(ln) and '可逆性' not in ln]
            if hits:
                rows.append((r, len(hits), hits[0]))
    rows.sort()
    for r, n, first in rows[:60]:
        print(f'- {r}({n} 處):{L.truncate(first, 90, "…")}')
    if len(rows) > 60:
        print(f'- …另有 {len(rows) - 60} 個檔')
    print(f'\n共 {len(rows)} 個檔。處理方式:消解、登記為待決單、或確認為刻意留白。\n')


def parse_pending_scenes():
    txt = L.read('世界設定/場景設定/README.md')
    res = []
    for blk in re.split(r'\n(?=## )', txt):
        if '待建' not in blk.split('\n', 1)[0]:
            continue
        for ln in blk.split('\n')[1:]:
            m = re.match(r'- ([^(:：\[]+)', ln)
            if m:
                res.append((m.group(1).strip(), re.findall(r'(?:PRO|P[123])-\d{3}', ln)))
    return res


def event_chapter(eid):
    ev = L.all_events().get(eid)
    if not ev:
        return None
    m = re.search(r'第\s*(\d+)\s*章', ev.get('章節', ''))
    return (ev['vol'], int(m.group(1))) if m else None


def section_b(ahead):
    print('## B. 場景待建\n')
    done = [(o['vol'], o['n']) for o in L.all_outlines() if L.prose_path(o['vol'], o['n'])]
    last = max(done, key=lambda x: L.chap_key(*x)) if done else None
    upcoming = [o for o in L.all_outlines() if not last or L.chap_key(o['vol'], o['n']) > L.chap_key(*last)][:ahead] if ahead else None
    up_keys = {(o['vol'], o['n']) for o in upcoming} if upcoming is not None else None
    n = 0
    _, ack_scenes = acknowledged()
    for name, eids in parse_pending_scenes():
        if ahead == 0 and name in ack_scenes:
            continue
        chs = sorted({c for c in (event_chapter(e) for e in eids) if c}, key=lambda x: L.chap_key(*x))
        if not chs:
            for o in L.all_outlines():
                if name in o['text']:
                    chs.append((o['vol'], o['n']))
                    break
        if up_keys is not None and not any(c in up_keys for c in chs):
            continue
        n += 1
        where = '、'.join(L.chap_label(*c) for c in chs[:4]) or '未能判定'
        print(f'- {name}:最早用於 {where}')
    print(f'\n共 {n} 項。補建後從 README 的待建清單移除。\n')


def section_c():
    print('## C. 大綱補丁段落(與本文並存)\n')
    n = 0
    for o in L.all_outlines():
        ps = [h for h in o['sections'] if re.search(r'增補|改版|對齊|DEC-\d+', h)]
        if ps:
            n += 1
            print(f"- {L.chap_label(o['vol'], o['n'])}〈{o['title']}〉:{'、'.join(ps)}")
    print(f'\n共 {n} 章。補丁優先於本文(寫作包已前置);待該章定稿後,把補丁併入本文並刪除補丁段落。\n')


def section_d():
    print('## D. 帳本待回補\n')
    n = 0
    for v, c, f in L.ledger_files():
        for r in L.parse_ledger(f)['tables'].get('新增事實', []):
            if r['回補'].startswith('待回補'):
                n += 1
                print(f"- {r['ID']}:{L.truncate(r['事實'], 80, '…')}")
    print(f'\n共 {n} 條。`python3 工具/回補清單.py` 有建議位置。\n')


def section_e():
    print('## E. 暫定名\n')
    left = 0
    for who in ('男主', '女主'):
        pth = f'角色/{who}/README.md'
        for ln in L.read(pth).split('\n'):
            if '暫定名' in ln:
                left += 1
                print(f'- {who}:{ln.strip()}')
    if not left:
        print('- (無)')
    print('\n(已於 DEC-079 定為正式名;敘述用名與名字階梯見 正文/技法/稱謂表.md。)\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--接下來', type=int, default=0)
    a = ap.parse_args()
    print('# 債務掃描\n')
    section_a()
    section_b(a.接下來)
    section_c()
    section_d()
    section_e()


if __name__ == '__main__':
    try:
        main()
    except BrokenPipeError:
        pass
