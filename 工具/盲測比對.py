#!/usr/bin/env python3
"""盲測比對:比較兩份獨立產出(不同模型、或同一模型不同次)的事實層差異,量化「可重現」。

用法:
    python3 工具/盲測比對.py A.帳本.md B.帳本.md          # 比較兩份帳本(建議:兩個模型各寫同一章後各自產出帳本)
    python3 工具/盲測比對.py --正文 A.md B.md             # 比較兩份成稿(抽出人名、數字、場景數、引言、字數)

方法與解讀見 手冊/盲測.md。輸出的「一致率」是事實欄位的相符比例,不是文筆相似度:
文字欄位用相似度門檻(預設 0.6)判斷「說的是同一件事」,所以結果是下限估計,最後仍要人看差異清單。
"""
import argparse
import difflib
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

TH = 0.6


def norm(s):
    return re.sub(r'[\s,，。;；:：、()（）「」『』\-—…·]', '', s)


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


class Tally:
    def __init__(self):
        self.rows = []  # (類別, 項目, 一致?, 說明)

    def add(self, cat, item, ok, note=''):
        self.rows.append((cat, item, ok, note))

    def report(self):
        cats = {}
        for cat, item, ok, note in self.rows:
            c = cats.setdefault(cat, [0, 0])
            c[1] += 1
            c[0] += 1 if ok else 0
        print('## 一致率\n')
        print('| 類別 | 相符 | 總數 | 一致率 |')
        print('|---|---|---|---|')
        tot_a = tot_b = 0
        for cat, (a, b) in cats.items():
            print(f'| {cat} | {a} | {b} | {a / b * 100:.0f}% |')
            tot_a += a
            tot_b += b
        if tot_b:
            print(f'| **合計** | {tot_a} | {tot_b} | **{tot_a / tot_b * 100:.0f}%** |')
        diffs = [r for r in self.rows if not r[2]]
        print(f'\n## 差異清單({len(diffs)} 項)\n')
        for cat, item, ok, note in diffs:
            print(f'- [{cat}] {item}:{note}')
        if not diffs:
            print('- (無)')


def compare_ledgers(pa, pb):
    a, b = L.parse_ledger(pa), L.parse_ledger(pb)
    for name, lg in (('A', a), ('B', b)):
        if lg['errors']:
            print(f'帳本 {name} 格式有問題:{lg["errors"]}')
    t = Tally()
    # 時間地點
    ta = {r['項目']: r['內容'] for r in a['tables'].get('時間地點', [])}
    tb = {r['項目']: r['內容'] for r in b['tables'].get('時間地點', [])}
    for k in ('起', '迄'):
        s = sim(ta.get(k, ''), tb.get(k, ''))
        t.add('時間地點', k, s >= TH, f'A「{ta.get(k, "")}」 / B「{tb.get(k, "")}」(相似度 {s:.2f})')
    # 章末人物狀態
    ca = {r['角色']: r for r in a['tables'].get('章末人物狀態', [])}
    cb = {r['角色']: r for r in b['tables'].get('章末人物狀態', [])}
    for role in sorted(set(ca) | set(cb)):
        if role not in ca or role not in cb:
            t.add('人物名單', role, False, '只出現在 ' + ('A' if role in ca else 'B'))
            continue
        t.add('人物名單', role, True)
        for fld in ('位置', '傷勢', '持物'):
            s = sim(ca[role][fld], cb[role][fld])
            t.add('人物狀態', f'{role}.{fld}', s >= TH, f'A「{ca[role][fld]}」 / B「{cb[role][fld]}」(相似度 {s:.2f})')
    # 物件
    oa = {r['ID']: r for r in a['tables'].get('物件', [])}
    ob = {r['ID']: r for r in b['tables'].get('物件', [])}
    for k in sorted(set(oa) | set(ob)):
        if k not in oa or k not in ob:
            t.add('物件', k, False, '只出現在 ' + ('A' if k in oa else 'B'))
        else:
            s = sim(oa[k]['持有者'], ob[k]['持有者'])
            t.add('物件', f'{k} 持有者', s >= TH, f'A「{oa[k]["持有者"]}」 / B「{ob[k]["持有者"]}」')
    # 數字
    def nums(lg):
        out = set()
        for r in lg['tables'].get('數字事實', []):
            out |= set(re.findall(r'[零〇一二兩三四五六七八九十百千萬半\d]+[^\s,，;；、]{0,2}', r['值']))
        return out
    na, nb = nums(a), nums(b)
    for x in sorted(na | nb):
        t.add('數字', x, x in na and x in nb, '只出現在 ' + ('A' if x in na else 'B') if not (x in na and x in nb) else '')
    # 專名、稱呼
    pa_, pb_ = ({re.split(r'[(（、]', r['名稱'])[0] for r in lg['tables'].get('新增專名', [])} for lg in (a, b))
    for x in sorted(pa_ | pb_):
        t.add('新增專名', x, x in pa_ and x in pb_, '只出現在 ' + ('A' if x in pa_ else 'B') if not (x in pa_ and x in pb_) else '')
    ca_ = {(r['誰'], r['稱呼誰'], r['用語']) for r in a['tables'].get('稱呼', [])}
    cb_ = {(r['誰'], r['稱呼誰'], r['用語']) for r in b['tables'].get('稱呼', [])}
    for x in sorted(ca_ | cb_):
        t.add('稱呼', '→'.join(x), x in ca_ and x in cb_, '只出現在 ' + ('A' if x in ca_ else 'B') if not (x in ca_ and x in cb_) else '')
    # 要點對照
    ma = {r['要點']: norm(r['場景']) for r in a['tables'].get('要點對照', [])}
    mb = {r['要點']: norm(r['場景']) for r in b['tables'].get('要點對照', [])}
    for k in sorted(set(ma) | set(mb), key=lambda x: int(re.sub(r'\D', '', x) or 0)):
        t.add('要點對照', f'要點 {k}', ma.get(k) == mb.get(k), f'A→{ma.get(k)} / B→{mb.get(k)}')
    t.report()


def compare_prose(pa, pb):
    import 帳本草稿 as D
    ba, bb = L.prose_body(L.read(pa)), L.prose_body(L.read(pb))
    t = Tally()
    names = set(L.parse_id_map()['角色']) - {'男主', '女主'}
    for al in L.NAME_ALIASES.values():
        names |= set(al)
    names = {n for n in names if len(n) >= 2}
    na = {n for n in names if n in ba}
    nb = {n for n in names if n in bb}
    for n in sorted(na | nb):
        t.add('出場人名', n, n in na and n in nb, '只出現在 ' + ('A' if n in na else 'B') if not (n in na and n in nb) else '')
    xa = {tok for tok, _ in D.number_candidates(ba, 200)}
    xb = {tok for tok, _ in D.number_candidates(bb, 200)}
    for x in sorted(xa | xb):
        t.add('數字片語', x, x in xa and x in xb, '只出現在 ' + ('A' if x in xa else 'B') if not (x in xa and x in xb) else '')
    sa, sb = len(re.split(r'\n＊\n', ba)), len(re.split(r'\n＊\n', bb))
    t.add('結構', '場景數', abs(sa - sb) <= 1, f'A {sa} 場 / B {sb} 場')
    ha, hb = L.han_count(ba), L.han_count(bb)
    t.add('結構', '漢字數(相差不超過 40%)', abs(ha - hb) / max(ha, hb, 1) <= 0.4, f'A {ha} / B {hb}')
    t.report()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--正文', action='store_true', dest='prose')
    a = ap.parse_args()
    (compare_prose if a.prose else compare_ledgers)(os.path.abspath(a.a), os.path.abspath(a.b))


if __name__ == '__main__':
    try:
        main()
    except BrokenPipeError:
        pass
