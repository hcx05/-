#!/usr/bin/env python3
"""帳本草稿:依成稿與章節大綱,產生一份預填一半的帳本草稿,減輕登記負擔。

用法:
    python3 工具/帳本草稿.py 第一部 2              # 印到標準輸出
    python3 工具/帳本草稿.py 第一部 2 --寫入       # 寫到 正文/計畫/第一部/第02章.帳本草稿.md

預填內容:標題與時間(取自大綱)、出場者列表、要點對照骨架、從正文抽出的「數字候選」與「疑似新人名」。
所有 `(待填)` 都必須由寫作者補完;補完後用 `工具/落稿.py 帳本` 存入正式位置。
帳本裡仍有 `(待填)` 時,正文檢查會報錯 E14,避免草稿被當成正式帳本。
這份草稿只是機械的起點:不替你判斷哪些事實值得登記,也不知道正文「確立」了什麼。
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

NUM = r'[零〇一二兩三四五六七八九十百千萬半幾\d]+'
UNIT = r'(?:個|名|人|騎|匹|頭|條|根|把|柄|張|塊|枚|顆|兩|文|錢|斤|里|丈|尺|寸|步|天|日|夜|年|個月|月|歲|針|碗|包|口|隻|間|扇|層|時辰|更|息|刻|盞|支|道|下|聲|成|倍)'


PEOPLE_U = {'人', '名', '騎', '匹', '頭'}
MEASURE_U = {'天', '日', '夜', '年', '個月', '月', '歲', '里', '丈', '尺', '寸', '步', '兩', '文', '錢', '斤', '時辰', '更', '息', '刻', '成', '倍'}
VAGUE = {'一', '兩', '半', '幾'}


def number_candidates(body, limit=25):
    """抽出可能是「之後會被引用的數字事實」的片語;刻意濾掉「一碗」「一間」這類泛稱。"""
    out, seen = [], set()
    for para in body.split('\n'):
        for m in re.finditer(f'({NUM})({UNIT})', para):
            num, unit, tok = m.group(1), m.group(2), m.group(0)
            if '幾' in num or tok in seen:
                continue
            if unit in PEOPLE_U and num in VAGUE:
                continue
            if unit in MEASURE_U and num in ('一',) and unit in ('天', '日', '夜', '年', '步', '月'):
                continue
            if unit not in PEOPLE_U and unit not in MEASURE_U and num in VAGUE:
                continue
            seen.add(tok)
            i = m.start()
            ctx = para[max(0, i - 14): i + len(tok) + 14].replace('\n', ' ')
            out.append((tok, ctx))
    return out[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('vol')
    ap.add_argument('n', type=int)
    ap.add_argument('--寫入', action='store_true')
    a = ap.parse_args()
    o = L.get_outline(a.vol, a.n)
    pth = L.prose_path(a.vol, a.n)
    if not o or not pth:
        raise SystemExit('找不到章節大綱或正文;請先組稿')
    body = L.prose_body(L.read(pth))
    scenes = [s_ for s_ in re.split(r'\n＊\n', body)]
    idm = L.parse_id_map()['角色']
    cast = [c for c in o['cast'] if c in idm]
    lines = [
        f"# 帳本 · {a.vol} · 第 {a.n} 章 {o['title']}", '',
        '> 狀態:草稿(由 工具/帳本草稿.py 產生,所有「(待填)」須補完)。格式見 [帳本說明](../README.md)。', '',
        '## 摘要', '- (待填:2 至 4 行,本章發生了什麼)', '',
        '## 時間地點', '| 項目 | 內容 |', '|---|---|',
        f"| 起 | (待填;大綱時間:{o['time']}) |", '| 迄 | (待填) |', '| 季節天候 | (待填) |', '',
        '## 章末人物狀態', '| 角色 | 位置 | 傷勢 | 持物 | 狀態 | 本章新知 | 本章新疑 |', '|---|---|---|---|---|---|---|',
    ]
    for c in cast:
        lines.append(f'| {c} | (待填) | (待填) | (待填) | (待填) | (待填) | (待填) |')
    lines += ['', '## 物件', '| ID | 名稱 | 持有者 | 狀態 |', '|---|---|---|---|', '| ITM-(待填) | (待填) | (待填) | (待填) |', '',
              '## 數字事實', '| 項目 | 值 | 備註 |', '|---|---|---|']
    cands = number_candidates(body)
    if cands:
        for tok, ctx in cands:
            lines.append(f'| (待填:這個數字指什麼) | {tok} | 候選;上下文:…{ctx}… |')
    else:
        lines.append('| (待填) | (待填) | |')
    lines += ['', '## 稱呼', '| 誰 | 稱呼誰 | 用語 | 備註 |', '|---|---|---|---|', '| (待填) | (待填) | (待填) | |', '',
              '## 新增專名', '| 類型 | 名稱 | 登記 | 備註 |', '|---|---|---|---|']
    # 疑似新人名:沿用正文檢查的啟發式
    import 正文檢查 as C
    errs, warns = C.check_file(pth, require_ledger=False)
    cand_names = []
    for code, _, msg in warns:
        if code == 'W06':
            cand_names = re.findall(r'([一-鿿]{2,3})×', msg)
    if cand_names:
        for nm in cand_names:
            lines.append(f'| 人物 | {nm} | 一次性 | 候選(說話標記前的稱呼),確認後保留或刪除 |')
    else:
        lines.append('| (待填) | (待填) | 一次性 | |')
    lines += ['', '## 新增事實', '| ID | 事實 | 回補 |', '|---|---|---|',
              f"| TXT-{L.VOL_CODE[a.vol]}-{a.n:02d}-01 | (待填:正文確立、之後可能被引用的事實) | 待回補 |", '',
              '## 伏筆動作', '| THR | 動作 | 備註 |', '|---|---|---|', '| (無) | | |', '',
              '## 要點對照', '| 要點 | 場景 | 備註 |', '|---|---|---|']
    for k, txt in o['points']:
        short = re.sub(r'\s+', ' ', txt)[:30]
        lines.append(f'| {k} | (待填:S1 至 S{len(scenes)}) | 大綱:{short}… |')
    lines += ['', '## 與大綱出入', '| 條目 | 處置 |', '|---|---|', '| (無) | |', '']
    text = '\n'.join(lines)
    if a.寫入:
        out = L.p('正文', '計畫', a.vol, f'第{a.n:02d}章.帳本草稿.md')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf8') as f:
            f.write(text)
        print(f'已寫入 {L.rel(out)};共 {len(scenes)} 場、{len(cands)} 個數字候選')
    else:
        print(text)


if __name__ == '__main__':
    main()
