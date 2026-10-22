#!/usr/bin/env python3
"""影響掃描:正文確立了新事實之後,找出「之後各章的大綱與事件描述」裡可能受影響的地方。
這是正文版的「變更傳播」:已定稿正文高於大綱(見 手冊/優先序與衝突.md),所以大綱要回頭對齊。

用法:
    python3 工具/影響掃描.py 序卷 3                    # 以該章帳本的物件、專名、稱呼、數字項目為關鍵詞
    python3 工具/影響掃描.py 序卷 3 --詞 虎符,鐵無情疤   # 另加人工指定的關鍵詞
    python3 工具/影響掃描.py --詞 秦七,喉風 --自 序卷 1   # 不指定章:從某章之後全部掃(清債用)

輸出:每個關鍵詞在「之後章節的大綱」「之後卷的事件描述」中出現的位置與前後文。
注意:輸出含後文大綱片段,是維護步驟,不要在正在寫作的上下文裡執行(會把後文劇透帶進現在);請另開上下文,只帶回「哪一章的哪句要加補丁」。
命中不代表矛盾,只代表需要人看一眼:大綱寫的和正文確立的是否一致。
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L


def core(name):
    """物件、專名的核心詞:去掉括號說明與逗號後面的部分。"""
    name = re.split(r'[(（,，;；:：]', name)[0].strip()
    name = re.sub(r'^(阿古的|七叔的|男主的|女主的|半枚|一對)', '', name)
    return name


def keywords_from_ledger(vol, n):
    pth = L.ledger_path(vol, n)
    if not os.path.exists(pth):
        raise SystemExit(f'沒有帳本:{L.rel(pth)}')
    lg = L.parse_ledger(pth)
    kw = []
    for r in lg['tables'].get('物件', []):
        kw.append(core(r['名稱']))
    for r in lg['tables'].get('新增專名', []):
        if r['登記'].startswith('已建檔'):
            continue  # 已建檔的角色、勢力本來就在大綱裡,不是新事實
        for part in re.split(r'[、]', r['名稱']):
            kw.append(core(part))
    for r in lg['tables'].get('稱呼', []):
        for part in re.split(r'[、/]', r['用語']):
            kw.append(core(part))
    ext = []
    for k in kw:
        ext.append(k)
        if len(k) >= 4:
            ext.append(k[-2:])  # 青銅虎符 → 虎符;阿古所贈狼牙 → 狼牙
    kw = ext
    seen, out = set(), []
    for k in kw:
        if len(k) >= 2 and k not in seen and k not in ('—', '未載', '她', '他'):
            seen.add(k)
            out.append(k)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('vol', nargs='?')
    ap.add_argument('n', nargs='?', type=int)
    ap.add_argument('--詞')
    ap.add_argument('--自', nargs=2, metavar=('卷', '章'))
    ap.add_argument('--每詞上限', type=int, default=6)
    a = ap.parse_args()
    kws = []
    if a.vol and a.n:
        start = (a.vol, a.n)
        kws += keywords_from_ledger(a.vol, a.n)
    elif a.自:
        start = (a.自[0], int(a.自[1]))
    else:
        ap.error('請給「卷 章」或 --自 卷 章')
    if a.詞:
        kws += [x.strip() for x in re.split(r'[,，、]', a.詞) if x.strip()]
    kws = list(dict.fromkeys(kws))
    k0 = L.chap_key(*start)
    print(f'# 影響掃描:自{L.chap_label(*start)}之後的章節大綱與事件描述\n關鍵詞:{"、".join(kws)}\n')
    outs = [o for o in L.all_outlines() if L.chap_key(o['vol'], o['n']) > k0]
    evs = [e for e in L.all_events().values()]
    total = 0
    for kw in kws:
        hits = []
        for o in outs:
            for ln in o['text'].split('\n'):
                if kw in ln:
                    hits.append((f"{L.chap_label(o['vol'], o['n'])} 大綱", ln.strip()))
        for e in evs:
            if L.chap_key(e['vol'], 1) <= k0 and e['vol'] == start[0]:
                continue
            blob = e.get('描述', '')
            if kw in blob and e['vol'] != '序卷':
                hits.append((f"{e['id']} 事件", blob))
        if not hits:
            continue
        if len(hits) > 25:
            print(f'## 「{kw}」({len(hits)} 處)\n- 常見詞,命中過多已略;如需核對請用更具體的詞。\n')
            continue
        total += len(hits)
        print(f'## 「{kw}」({len(hits)} 處)')
        for src, ln in hits[: a.每詞上限]:
            i = ln.find(kw)
            lo, hi = max(0, i - 28), min(len(ln), i + 48)
            print(f'- {src}:…{ln[lo:hi]}…')
        if len(hits) > a.每詞上限:
            print(f'- (另有 {len(hits) - a.每詞上限} 處,用 --每詞上限 調高)')
        print()
    print(f'共 {total} 處命中。逐一核對:大綱寫的與已定稿正文是否一致;不一致時,正文為準,大綱加補丁段落(標題含「改版」或「增補」)。')


if __name__ == '__main__':
    try:
        main()
    except BrokenPipeError:
        pass
