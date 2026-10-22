#!/usr/bin/env python3
"""建索引:由現有 Markdown 導出 索引/*.json(章節、事件、人物、術語、伏筆),供工具與外部程式使用。

用法:
    python3 工具/建索引.py          # 重建 索引/
    python3 工具/建索引.py --檢查   # 只檢查是否最新,過期則結束碼 1

索引是導出物,請勿手改;來源有變動就重建。
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

OUT = '索引'


def source_files():
    files = ['設計規範/ID對照.md', '設計規範/術語表.md', '狀態/伏筆登記簿.md', '正文/技法/稱謂表.md']
    for v in L.VOLS:
        for name in ('事件描述.md',):
            if L.exists(f'故事線/{v}/{name}'):
                files.append(f'故事線/{v}/{name}')
        files += [L.rel(x) for x in L.outline_paths(v)]
    return sorted(set(f for f in files if L.exists(f)))


def build():
    srcs = source_files()
    digest = L.sha('\n'.join(f'{f}\n{L.read(f)}' for f in srcs))
    meta = {'說明': '導出檔,請勿手改;由 python3 工具/建索引.py 產生', '來源雜湊': digest, '來源檔數': len(srcs)}
    chapters = []
    for o in L.all_outlines():
        chapters.append({
            '卷': o['vol'], '章': o['n'], '標題': o['title'], '大綱': o['path'],
            '視角': o['pov'], '時間': o['time'], '預計字數': o['budget'],
            '對應事件': o['events'], '提及事件': o['mentioned'], '場景': o['places'], '出場': o['cast'],
            '要點數': len(o['points']),
            '有正文': L.prose_path(o['vol'], o['n']) is not None,
            '有帳本': L.exists(L.rel(L.ledger_path(o['vol'], o['n']))),
        })
    events = {}
    for eid, ev in sorted(L.all_events().items()):
        events[eid] = {'卷': ev['vol'], '序號': ev['serial'], '名稱': ev['name'], '時間': ev.get('時間', ''),
                       '章節': ev.get('章節', ''), '出場': ev['cast']}
    idm = L.parse_id_map()
    people = []
    for name, (cid, path) in idm['角色'].items():
        d = path.rstrip('/')
        people.append({'ID': cid, '名稱': name, '路徑': path, '別名': L.NAME_ALIASES.get(name, []),
                       '設定卷': [v for v in L.VOLS if L.exists(f'{d}/設定/{v}.md')],
                       '記憶卷': [v for v in L.VOLS if L.exists(f'{d}/成長/記憶/{v}.md')]})
    orgs = [{'ID': i, '名稱': n, '路徑': pth} for n, (i, pth) in idm['勢力'].items()]
    places = [{'ID': i, '名稱': n, '路徑': pth} for n, (i, pth) in idm['場景'].items()]
    terms = L.parse_terms()
    threads = []
    for head, cols, trs in L.md_tables(L.read('狀態/伏筆登記簿.md')):
        if cols and cols[0] == 'ID':
            for r in trs:
                threads.append(dict(zip(cols, r)))
    data = {
        '章節.json': {'_meta': meta, '章節': chapters},
        '事件.json': {'_meta': meta, '事件': events},
        '人物.json': {'_meta': meta, '角色': people, '勢力': orgs, '場景': places},
        '術語.json': {'_meta': meta, '術語': terms},
        '伏筆.json': {'_meta': meta, '伏筆': threads},
    }
    return {k: json.dumps(v, ensure_ascii=False, indent=1) + '\n' for k, v in data.items()}, digest


def main():
    data, digest = build()
    out = L.p(OUT)
    if '--檢查' in sys.argv:
        bad = []
        for name, text in data.items():
            path = os.path.join(out, name)
            if not os.path.exists(path) or open(path, encoding='utf8').read() != text:
                bad.append(name)
        if bad:
            print('索引已過期:' + '、'.join(bad) + ';請執行 python3 工具/建索引.py')
            sys.exit(1)
        print('索引為最新')
        return
    os.makedirs(out, exist_ok=True)
    for name, text in data.items():
        with open(os.path.join(out, name), 'w', encoding='utf8') as f:
            f.write(text)
    print(f'已寫入 {OUT}/({len(data)} 個檔,來源雜湊 {digest})')


if __name__ == '__main__':
    main()
