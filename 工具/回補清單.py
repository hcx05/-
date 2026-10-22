#!/usr/bin/env python3
"""回補清單:列出帳本中「待回補」的新增事實,並依內容建議該寫回哪些設定檔。

用法:
    python3 工具/回補清單.py            # 只列待回補
    python3 工具/回補清單.py --全部     # 連同已回補、無需回補一起列(核對用)

回補完成後,把帳本該列的「回補」欄改成 `已回補→路徑`(路徑須存在,檢查腳本會驗證)。
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L


def suggest(text, vol, cast=()):
    """依事實內文提到的名稱,建議回補位置。"""
    idm = L.parse_id_map()
    out = []
    for name, (cid, path) in idm['角色'].items():
        names = [name] + L.NAME_ALIASES.get(name, [])
        if name in ('男主', '女主') or len(name) >= 2:
            if any(n in text for n in names if len(n) >= 2) or (name in ('男主', '女主') and name in text):
                d = path.rstrip('/')
                if L.exists(f'{d}/成長/記憶/{vol}.md'):
                    out.append(f'{d}/成長/記憶/{vol}.md')
    for name, (cid, path) in idm['場景'].items():
        if len(name) >= 2 and name in text:
            out.append(path.rstrip('/') + '/建模描述.md')
    for name, (cid, path) in idm['勢力'].items():
        if len(name) >= 2 and name in text:
            out.append(path if path.endswith('.md') else path.rstrip('/') + '.md')
    if not out:
        for name in cast:
            if name in idm['角色']:
                d = idm['角色'][name][1].rstrip('/')
                out.append(f'{d}/成長/記憶/{vol}.md')
    seen, res = set(), []
    for x in out:
        if x not in seen and L.exists(x):
            seen.add(x)
            res.append(x)
    return res[:5]


def main():
    show_all = '--全部' in sys.argv
    n_todo = 0
    for v, c, f in L.ledger_files():
        lg = L.parse_ledger(f)
        rows = lg['tables'].get('新增事實', [])
        o = L.get_outline(v, c)
        cast = o['cast'] if o else []
        sel = [r for r in rows if show_all or r['回補'].startswith('待回補')]
        if not sel:
            continue
        print(f'## {L.chap_label(v, c)} {lg.get("title", "")}({L.rel(f)})')
        for r in sel:
            if r['回補'].startswith('待回補'):
                n_todo += 1
            print(f"- {r['ID']}〔{r['回補']}〕{L.truncate(r['事實'], 120, '…')}")
            if r['回補'].startswith('待回補'):
                for sug in suggest(r['事實'], v, cast):
                    print(f'    建議回補到:{sug}')
    print(f'\n待回補共 {n_todo} 條。')


if __name__ == '__main__':
    main()
