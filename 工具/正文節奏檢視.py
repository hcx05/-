#!/usr/bin/env python3
"""正文節奏檢視:列出疑似碎片化的敘述段落、重複句型與措辭,供編輯正文時參考。

用法:
    python3 工具/正文節奏檢視.py 正文/序卷/第1章_斷碑村.md [更多檔案或資料夾...]
    python3 工具/正文節奏檢視.py 正文/序卷            # 資料夾:依檔名順序讀取其中的 .md
    選項:--short N 短段字數上限(預設 30 個漢字)  --limit N 每項最多列出幾筆(預設 25)
          --all 一併列出夾在對白之間的短敘述段(預設只提示數量)

只讀不改,結束碼恆為 0(檔案不存在除外)。輸出是閱讀時的提示,不是文學上的通過或失敗:
有意的呼應、重要時刻的獨句段落、對白間的動作句都是正常寫法,請依實際閱讀判斷。
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

HANZI = re.compile(r'[一-鿿]')
QUOTE = re.compile(r'「[^」]*」|『[^』]*』')
SENT_END = re.compile(r'[。！？]+')
SPEECH_VERB = re.compile(r'(?<![知街報味軌正古大小鐵])(道|問道|答道|回道|問|答|應|喊|笑|喝)(?=[：:，。、]|$)')

# 常見的人工句型(僅作計數提示,不是禁用清單)
PATTERNS = [
    ('不是…而是', re.compile(r'不是[^。！？]{1,30}?而是')),
    ('沒有…也沒有', re.compile(r'沒有[^。！？]{1,25}?也沒有')),
    ('沒有/並非…只是', re.compile(r'(?:沒有|並非|並不|不是)[^。！？「」]{1,25}?(?:只是|只有)')),
    ('直到…才', re.compile(r'直到[^。！？]{1,25}?才')),
    ('那一刻/這才明白', re.compile(r'那一刻|這一刻|這才(?:明白|懂|知道)|終於(?:明白|懂得|知道)')),
    ('像是/彷彿/仿佛', re.compile(r'彷彿|仿佛|像是|宛如|如同')),
    ('忽然/猛地/驟然', re.compile(r'忽然|猛地|猛然|驟然|倏地|陡然')),
    ('只見', re.compile(r'只見')),
    ('竟/原來', re.compile(r'竟然|竟(?=[一-鿿])|原來')),
    ('破折號/省略號', re.compile(r'——|……')),
]


def read_paragraphs(path):
    """回傳 [(行號, 文字)];排除標題、章節註記、場景分隔與空行。"""
    out = []
    with open(path, encoding='utf8') as f:
        for no, line in enumerate(f, 1):
            t = line.strip()
            if not t or t.startswith('#') or t.startswith('>'):
                continue
            if re.fullmatch(r'[＊*＊\-—─·•◇◆\s]{1,12}', t):
                continue
            out.append((no, t))
    return out


def classify(text):
    """dialogue:含引號對白(含「某某道:「…」」);narration:純敘述。"""
    has_quote = any(c in text for c in '「」『』')  # 含跨段對白的收尾段
    outside = QUOTE.sub('', text)
    n_hz = len(HANZI.findall(outside))
    sentences = len([s for s in SENT_END.split(outside) if HANZI.search(s)])
    return {
        'kind': 'dialogue' if has_quote else 'narration',
        'hanzi': n_hz if not has_quote else len(HANZI.findall(text)),
        'sentences': max(sentences, 1) if n_hz else 0,
        'tagged': bool(has_quote and SPEECH_VERB.search(outside)),
    }


def trunc(s, n=46):
    return s if len(s) <= n else s[:n] + '…'


def analyse_file(path, short):
    paras = []
    for no, text in read_paragraphs(path):
        info = classify(text)
        info.update(line=no, text=text)
        paras.append(info)
    for i, p in enumerate(paras):
        p['frag'] = p['kind'] == 'narration' and (p['sentences'] <= 1 or p['hanzi'] <= short) \
            and p['hanzi'] <= 60
        prev_d = i > 0 and paras[i - 1]['kind'] == 'dialogue'
        next_d = i + 1 < len(paras) and paras[i + 1]['kind'] == 'dialogue'
        p['between'] = prev_d and next_d
    return paras


def find_zones(paras, run_min=3, win=6, win_min=4):
    """疑似連續短段:連續 ≥run_min 個碎片段,或任意 win 段內 ≥win_min 個碎片段。"""
    n = len(paras)
    mark = [False] * n
    i = 0
    while i < n:
        if paras[i]['frag']:
            j = i
            while j < n and paras[j]['frag']:
                j += 1
            if j - i >= run_min:
                for k in range(i, j):
                    mark[k] = True
            i = j
        else:
            i += 1
    for s in range(0, max(n - win + 1, 1)):
        window = range(s, min(s + win, n))
        if sum(1 for k in window if paras[k]['frag']) >= win_min:
            for k in window:
                if paras[k]['frag']:
                    mark[k] = True
    zones = []
    i = 0
    while i < n:
        if mark[i]:
            j = i
            while j + 1 < n and (mark[j + 1] or (j + 2 < n and mark[j + 2])):
                j += 1
            zones.append((i, j))
            i = j + 1
        else:
            i += 1
    return zones


def repeated_phrases(files_paras, min_len=6, ext_cap=24):
    """跨檔找重複措辭:以句子為界的 min_len 字片段,向兩側擴到所有出現處共同的最長片段。"""
    sents = []  # (檔名, 行號, 句子的純漢字+標點文字)
    for name, paras in files_paras:
        for p in paras:
            for s in re.split(r'[。！？；\n]', p['text']):
                s = re.sub(r'[「」『』\s]', '', s)
                if len(s) >= min_len:
                    sents.append((name, p['line'], s))
    index = defaultdict(list)
    for si, (_, _, s) in enumerate(sents):
        seen = set()
        for k in range(len(s) - min_len + 1):
            g = s[k:k + min_len]
            if g in seen:
                continue
            seen.add(g)
            index[g].append((si, k))
    results = {}
    for g, occ in index.items():
        if len(occ) < 2 or not all(HANZI.search(c) for c in g[:2]):
            continue
        lo = 0
        while lo < ext_cap and all(k - lo - 1 >= 0 for _, k in occ) and \
                len({sents[si][2][k - lo - 1] for si, k in occ}) == 1:
            lo += 1
        hi = 0
        while hi < ext_cap and all(k + min_len + hi < len(sents[si][2]) for si, k in occ) and \
                len({sents[si][2][k + min_len + hi] for si, k in occ}) == 1:
            hi += 1
        si0, k0 = occ[0]
        phrase = sents[si0][2][k0 - lo:k0 + min_len + hi].strip('，、：；,:')
        if len(HANZI.findall(phrase)) < min_len:
            continue
        where = sorted({(sents[si][0], sents[si][1]) for si, _ in occ})
        results[phrase] = where
    # 去掉被更長片段包含且出現處相同的項
    phrases = sorted(results, key=len, reverse=True)
    kept = []
    for ph in phrases:
        if any(ph in other and results[ph] == results[other] for other in kept):
            continue
        kept.append(ph)
    return [(ph, results[ph]) for ph in kept if len(results[ph]) >= 2]


def short_name(path):
    return os.path.basename(path).replace('.md', '')


def main():
    ap = argparse.ArgumentParser(description='正文節奏檢視(只讀、僅供參考)')
    ap.add_argument('paths', nargs='+', help='正文 .md 檔案或資料夾')
    ap.add_argument('--short', type=int, default=30, help='短敘述段的漢字數上限(預設 30)')
    ap.add_argument('--limit', type=int, default=25, help='每項最多列出幾筆(預設 25)')
    ap.add_argument('--all', action='store_true', help='一併列出夾在對白之間的短敘述段')
    args = ap.parse_args()

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files += sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith('.md')
                            and f.startswith('第'))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print(f'找不到檔案:{p}', file=sys.stderr)
            return 2

    data = [(short_name(f), analyse_file(f, args.short)) for f in files]
    print('正文節奏檢視(提示用;有意的呼應與必要的短段不是錯誤,請依閱讀判斷)')
    print(f'短段 = 純敘述段,單句或 ≤{args.short} 個漢字')

    for name, paras in data:
        narr = [p for p in paras if p['kind'] == 'narration']
        dial = [p for p in paras if p['kind'] == 'dialogue']
        frags = [p for p in narr if p['frag']]
        single = [p for p in narr if p['sentences'] <= 1 and p['hanzi'] <= 60]
        between = [p for p in frags if p['between']]
        print(f'\n=== {name} ===')
        print(f'段落 {len(paras)}:敘述 {len(narr)}、含對白 {len(dial)};'
              f'單句敘述段 {len(single)}、短敘述段共 {len(frags)}'
              f'(其中夾在對白間 {len(between)})')

        shown = [p for p in frags if args.all or not p['between']]
        if shown:
            print(f'-- 單句/短敘述段(前 {min(len(shown), args.limit)}/{len(shown)} 筆)')
            for p in shown[:args.limit]:
                tag = '單句' if p['sentences'] <= 1 else f'{p["sentences"]}句'
                print(f'  L{p["line"]} [{tag},{p["hanzi"]}字] {trunc(p["text"])}')

        zones = find_zones(paras)
        if zones:
            print(f'-- 疑似連續短段區 {len(zones)} 處(連續 ≥3 個短段,或 6 段內 ≥4 個)')
            for a, b in zones[:args.limit]:
                lo, hi = max(a - 1, 0), min(b + 1, len(paras) - 1)
                print(f'  L{paras[a]["line"]}-L{paras[b]["line"]}:共 {b - a + 1} 段')
                for k in range(lo, hi + 1):
                    p = paras[k]
                    mark = '·' if lo <= k < a or k > b else '▸'
                    kind = '白' if p['kind'] == 'dialogue' else ('短' if p['frag'] else '敘')
                    print(f'    {mark} L{p["line"]} {kind} {trunc(p["text"], 40)}')

        # 對白標籤:連續多段全都帶標籤
        run = []
        runs = []
        for p in paras:
            if p['kind'] == 'dialogue' and p['tagged']:
                run.append(p)
            else:
                if len(run) >= 4:
                    runs.append(run)
                run = []
        if len(run) >= 4:
            runs.append(run)
        d_tagged = sum(1 for p in dial if p['tagged'])
        print(f'-- 對白標籤:含對白 {len(dial)} 段,疑似帶說話動詞 {d_tagged} 段'
              + (f';連續 ≥4 段都帶標籤 {len(runs)} 處:'
                 + '、'.join(f'L{r[0]["line"]}-L{r[-1]["line"]}' for r in runs[:8]) if runs else ''))

        total_hz = sum(len(HANZI.findall(p['text'])) for p in paras) or 1
        row = []
        for label, rx in PATTERNS:
            c = sum(len(rx.findall(p['text'])) for p in paras)
            if c:
                row.append(f'{label} {c}')
        print(f'-- 句型計數(漢字 {total_hz} 字;計數僅供參考):' + ('、'.join(row) if row else '無'))

        opener = Counter()
        for p in narr:
            for s in re.split(r'[。！？]', p['text']):
                s = s.strip('，、 ')
                if len(s) >= 3 and HANZI.match(s[:2]):
                    opener[s[:2]] += 1
        top = [f'{k}×{v}' for k, v in opener.most_common(8) if v >= 5]
        if top:
            print('-- 敘述句首高頻(人名與代詞居多,留意「他想」「他把」之類的慣性):' + '、'.join(top))

    if len(data) >= 2:
        print('\n=== 跨章重複措辭(≥6 字,出現 ≥2 處;含對白,未判斷是否有意呼應)===')
        reps = repeated_phrases(data)
        reps.sort(key=lambda x: (-len({w[0] for w in x[1]}), -len(x[1]), -len(x[0])))
        for ph, where in reps[:args.limit]:
            files_hit = sorted({w[0] for w in where})
            locs = ' '.join(f'{w[0][:3]}L{w[1]}' for w in where[:6])
            more = '…' if len(where) > 6 else ''
            print(f'  「{trunc(ph, 30)}」×{len(where)}[{",".join(f[:3] for f in files_hit)}] {locs}{more}')
        if len(reps) > args.limit:
            print(f'  …另有 {len(reps) - args.limit} 組(--limit 可放寬)')
        if not reps:
            print('  (無)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
