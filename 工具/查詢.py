#!/usr/bin/env python3
"""查詢:取某個名稱(角色、勢力、場景、術語、物件、專名)在「截至某章」時的資料,自動排除未來內容。

用法:
    python3 工具/查詢.py 阿古 --至 第一部2          # 截至第一部第 2 章(含本章事件,不含之後)
    python3 工具/查詢.py 血月教 --至 序卷3 --全文   # 不截短
    python3 工具/查詢.py 阿古                      # 沒給 --至:只用已有帳本的最後一章為界

「至」寫法:序N、一N、二N、三N,或「第一部2」。
限制:勢力檔、場景檔與世界設定不分卷,可能含後續卷的內容,輸出會標明「未依章過濾」,寫作時只當背景,不當既成事實。
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

EVID = re.compile(r'(?:PRO|P[123])-\d{3}')


def parse_to(s):
    if not s:
        files = L.ledger_files()
        if files:
            v, c, _ = files[-1]
            return v, c + 1
        return '序卷', 1
    t = L.parse_chap_token(s)
    if t:
        return t
    m = re.fullmatch(r'(序卷|第[一二三]部)\s*(?:第)?\s*(\d+)\s*章?', s.strip())
    if m:
        return m.group(1), int(m.group(2))
    raise SystemExit(f'看不懂「--至 {s}」,請寫成 序3、一2 或 第一部2')


def cutoff_of(vol, n):
    o = L.get_outline(vol, n)
    return L.chapter_cutoff(o) if o else 0


def clip(s, n, full):
    return s if full else L.truncate(s, n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('名稱')
    ap.add_argument('--至', dest='to')
    ap.add_argument('--全文', action='store_true')
    a = ap.parse_args()
    vol, n = parse_to(a.to)
    name = a.名稱
    cutoff = cutoff_of(vol, n)
    idm = L.parse_id_map()
    # 別名 → 正名
    for canon, al in L.NAME_ALIASES.items():
        if name in al:
            name = canon
    out = [f'# 查詢「{a.名稱}」· 截至{vol}第 {n} 章(含)']
    hit = False

    # 1 帳本
    led = [lg for lg in L.ledgers_before(vol, n)]
    cur = L.ledger_path(vol, n)
    if os.path.exists(cur):
        led.append(L.parse_ledger(cur))
    rows = []
    for lg in led:
        if 'vol' not in lg:
            continue
        tag = L.chap_label(lg['vol'], lg['n'])
        for tname, recs in lg['tables'].items():
            for r in recs:
                if any(name in v or a.名稱 in v for v in r.values()):
                    rows.append(f'- [{tag} {tname}] ' + ';'.join(f'{k}:{v}' for k, v in r.items() if v))
    if rows:
        hit = True
        out.append('\n## 帳本記錄(已定稿正文確立的事實,效力高於設定檔)\n' + '\n'.join(rows))

    # 2 角色
    if name in idm['角色']:
        hit = True
        cid, path = idm['角色'][name]
        d = path.rstrip('/')
        out.append(f'\n## 角色 {name}({cid})')
        for v in L.VOLS[: L.vol_rank(vol) + 1]:
            sp = f'{d}/設定/{v}.md'
            if L.exists(sp):
                out.append(f'\n### 設定·{v}(時點:該卷開篇,不含後續劇情)\n' + clip(L.read(sp), 1800, a.全文))
        for v in L.VOLS[: L.vol_rank(vol) + 1]:
            mp = f'{d}/成長/記憶/{v}.md'
            if not L.exists(mp):
                continue
            blocks = []
            for blk in re.split(r'\n(?=### )', L.read(mp)):
                if not blk.startswith('### '):
                    continue
                ids = EVID.findall(blk.split('\n', 1)[0])
                if v == vol:
                    sers = [L.event_serial(i) for i in ids]
                    if not ids or any(s is None or s > cutoff for s in sers):
                        continue
                blocks.append(blk.strip())
            if blocks:
                out.append(f'\n### 記憶·{v}(僅含截至本章事件的段落)\n' + clip('\n\n'.join(blocks), 2400, a.全文))
        skipped = [v for v in L.VOLS[L.vol_rank(vol) + 1:] if L.exists(f'{d}/設定/{v}.md') or L.exists(f'{d}/成長/記憶/{v}.md')]
        if skipped:
            out.append(f'\n(未來卷資料已排除:{"、".join(skipped)})')

    # 3 勢力、場景
    for kind in ('勢力', '場景'):
        if name in idm[kind]:
            hit = True
            cid, path = idm[kind][name]
            fp = path if path.endswith('.md') else path.rstrip('/') + '/建模描述.md'
            if L.exists(fp):
                out.append(f'\n## {kind} {name}({cid})· 未依章過濾:此檔不分卷,可能含後續內容,僅當背景\n' + clip(L.read(fp), 2200, a.全文))

    # 4 術語
    for t in L.parse_terms():
        if name == t['標準'] or name in t['避免']:
            hit = True
            bad = '、'.join(t['避免']) or '—'
            out.append(f"\n## 術語 {t['標準']}:{t['說明']}(避免寫法:{bad})")

    # 5 事實登錄(含該名稱者)
    facts = [f for f in L.parse_facts() if a.名稱 in f['事實']]
    if facts:
        hit = True
        out.append('\n## 事實登錄(含此名稱;部分條目涉及後續卷,僅當硬規則參考)\n' + '\n'.join(f"- {f['ID']}:{clip(f['事實'], 200, a.全文)}" for f in facts[:15]))

    # 6 稱謂表
    nm = [r for r in L.naming_for(vol, n) if r['角色'] == name]
    for r in nm:
        out.append(f"\n## 稱謂表:{r['角色']}  可用「{'、'.join(r['可用'])}」 禁用「{'、'.join(r['禁用'])}」 待決「{'、'.join(r['待決'])}」")
    for r in L.reveals_blocked(vol, n):
        if r['詞'] in a.名稱 or a.名稱 in r['詞']:
            out.append(f"\n## 揭露限制:「{r['詞']}」最早到{L.chap_label(*r['first'])}才可出現在正文({r['強度']};依據:{r['依據']})。可作為作者背景,不得寫進本章。")
    if not hit and not nm:
        out.append('\n(查無資料。確認名稱是否正確,或該物尚未登記;不要自行補設定,必要時開待決單。)')
    print('\n'.join(out))


if __name__ == '__main__':
    main()
