#!/usr/bin/env python3
"""聲口萃取:從已定稿正文抽出每個角色的對白,供建立或補充「聲口卡」。唯讀。

用法:
    python3 工具/聲口萃取.py                 # 所有定稿章,每人列最具代表性的幾句
    python3 工具/聲口萃取.py 阿古 --每人 12   # 只看某人
    python3 工具/聲口萃取.py --卷 第一部      # 只看某卷

辨識方式:`某某道:「…」`、`「…」某某道` 兩種標記;沒有說話標記的對白不抽(寧缺勿錯)。
輸出只是素材:聲口卡要寫的是**習慣**(話量、節奏、口頭禪、禁忌),不是挑金句。
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

VERBS = r'(?:低聲|冷冷|淡淡|大聲|笑著|輕聲|沉聲)?(?:問道|說道|笑道|喝道|罵道|答道|嘆道|叫道|道)'


def speakers():
    names = set(L.parse_id_map()['角色']) - {'男主', '女主'}
    canon = {n: n for n in names if len(n) >= 2}
    for c, al in L.NAME_ALIASES.items():
        for a in al:
            canon[a] = c
    canon['懷川'] = '男主'
    canon['陸懷川'] = '男主'
    return canon


def extract(text, canon):
    names = sorted(canon, key=len, reverse=True)
    alt = '|'.join(re.escape(n) for n in names)
    out = []
    for m in re.finditer(rf'({alt}){VERBS}[:：，,]?「([^」]{{3,80}})」', text):
        out.append((canon[m.group(1)], m.group(2)))
    for m in re.finditer(rf'「([^」]{{3,80}})」[，,]?({alt}){VERBS}', text):
        out.append((canon[m.group(2)], m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('名', nargs='?')
    ap.add_argument('--卷')
    ap.add_argument('--每人', type=int, default=6)
    a = ap.parse_args()
    canon = speakers()
    want = canon.get(a.名, a.名) if a.名 else None
    lines = {}
    for v, n, t, f in L.prose_files(a.卷):
        body = L.prose_body(L.read(f))
        for who, s in extract(body, canon):
            lines.setdefault(who, []).append((L.chap_label(v, n), s))
    for who, items in sorted(lines.items(), key=lambda kv: -len(kv[1])):
        if want and who != want:
            continue
        # 偏好長度適中、不重複的句子
        seen, pick = set(), []
        for tag, s in sorted(items, key=lambda x: abs(len(x[1]) - 18)):
            if s not in seen:
                seen.add(s)
                pick.append((tag, s))
        avg = sum(len(s) for _, s in items) / len(items)
        print(f'## {who}(抽到 {len(items)} 句,平均 {avg:.0f} 字)')
        for tag, s in pick[: a.每人]:
            print(f'- [{tag}] 「{s}」')
        print()


if __name__ == '__main__':
    try:
        main()
    except BrokenPipeError:
        pass
