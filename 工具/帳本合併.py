#!/usr/bin/env python3
"""帳本合併:依章序折疊 正文/帳本/ 下所有帳本,導出 正文/帳本/累積狀態.md。

用法:
    python3 工具/帳本合併.py            # 重建累積狀態.md
    python3 工具/帳本合併.py --檢查     # 只檢查是否最新,過期則結束碼 1
累積狀態是導出檔,請勿手改。
"""
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import 寫作庫 as L

OUT = '正文/帳本/累積狀態.md'


def table(cols, rows):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    for r in rows:
        out.append('| ' + ' | '.join(str(r.get(c, '')).replace('\n', ' ') for c in cols) + ' |')
    return '\n'.join(out)


def build():
    files = L.ledger_files()
    ledgers = [L.parse_ledger(f) for v, c, f in files]
    st = L.fold_ledgers(ledgers)
    digest = L.sha('\n'.join(L.read(f) for v, c, f in files))
    last = L.chap_label(*st['last']) if st['last'] else '—'
    lines = [
        '# 累積狀態(導出檔,請勿手改)',
        '',
        f'> 截至:{last}(帳本 {len(files)} 份;雜湊 {digest})。由 `python3 工具/帳本合併.py` 折疊 [帳本](README.md) 產生;帳本有改動時重建,`工具/檢查.py` 會檢查是否最新。',
        '> 人物與物件取最近一章的記錄;稱呼取最近一次;數字、專名、新增事實逐章累積。章欄中「序1」=序卷第 1 章,「一2」=第一部第 2 章。',
        '',
        '## 人物(最近一次記錄)',
        table(['角色', '章', '位置', '傷勢', '持物', '狀態', '本章新知', '本章新疑'], st['chars'].values()),
        '',
        '## 物件',
        table(['ID', '章', '名稱', '持有者', '狀態'], st['items'].values()),
        '',
        '## 稱呼(最近一次)',
        table(['誰', '稱呼誰', '用語', '章', '備註'], st['calls'].values()),
        '',
        '## 數字事實',
        table(['章', '項目', '值', '備註'], st['numbers']),
        '',
        '## 新增專名',
        table(['章', '類型', '名稱', '登記', '備註'], st['names']),
        '',
        '## 新增事實',
        table(['ID', '章', '事實', '回補'], st['facts']),
        '',
    ]
    return '\n'.join(lines)


def main():
    text = build()
    path = L.p(OUT)
    if '--檢查' in sys.argv:
        try:
            cur = open(path, encoding='utf8').read()
        except FileNotFoundError:
            cur = ''
        if cur != text:
            print('累積狀態.md 已過期,請執行 python3 工具/帳本合併.py')
            sys.exit(1)
        print('累積狀態.md 為最新')
        return
    with open(path, 'w', encoding='utf8') as f:
        f.write(text)
    print(f'已寫入 {OUT}')


if __name__ == '__main__':
    main()
