#!/usr/bin/env python3
"""正文句式慣性掃描(階段 G2.1)。只列「提示」,不判通過或失敗,結束碼恆為 0。

依據 正文/寫作規範.md 第三節與第九節:規範要留意的是「短距離內的慣性」,不是禁用詞;
自動偵測只是提示,不是文學上的通過或失敗判決。本工具因此只做三件事:
  1. 計數:規範第三節列的句型與高頻詞,折成每萬漢字的密度;
  2. 相鄰章比較:同一類在連續兩章都偏高時,標出來,供人決定是否真的是「重演」;
  3. 章內重複:同一章內反覆出現的短語(扣掉人名),以及段首起句的集中度。

用法:
  python3 工具/句式掃描.py                 # 掃 正文/ 下所有 第N章_*.md
  python3 工具/句式掃描.py 正文/第一部      # 掃指定資料夾
  python3 工具/句式掃描.py 檔案1.md 檔案2.md

章的相鄰關係依檔名排序(卷序:序卷、第一部、第二部、第三部;卷內依章號)。
"""
import collections, glob, os, re, statistics, sys

sys.dont_write_bytecode = True

VOLS = ['序卷', '第一部', '第二部', '第三部']
HAN = re.compile(r'[一-鿿]')

# 規範第三節的句型。regex 只抓「形」,是不是真有新資訊要人讀。
# 正文用全形標點,這裡一律用 \uXXXX 跳脫(ff0c 逗號、ff1b 分號、ff01 驚嘆號、ff1f 問號、ff1a 冒號、3001 頓號)。
C = r'[,\uff0c]'            # 逗號
E = r'[。!?\uff01\uff1f]'   # 句末
PATTERNS = collections.OrderedDict([
    ('連續否定', re.compile(r'沒有[^。\n]{1,16}也沒有|既不[^。\n]{1,12}' + C + r'?亦不|並無[^。\n]{1,12}也無')),
    ('先否定後定義', re.compile(r'不是[^。\n]{1,20}而是|並非[^。\n]{1,20}(?:只是|而是)|(?:他|她|它)沒有[^。\n]{1,16}' + C + '只是')),
    ('公式化頓悟', re.compile(r'(?:直到|等到)這[時刻][^。\n]{0,10}才(?:明白|知道|懂|發現|意識)|那一刻' + C + r'?[^。\n]{0,10}(?:終於|才)(?:明白|知道|懂)')),
    ('三連同字起句', re.compile(r'(.)[^,\uff0c。\n]{1,8}' + C + r'\1[^,\uff0c。\n]{1,8}' + C + r'\1[^,\uff0c。\n]{1,8}[。;\uff1b]')),
])
WORDS = ['只見', '忽然', '竟', '原來', '彷彿']
MARKS = collections.OrderedDict([('破折號', '——'), ('省略號', '……')])

# 提示門檻(每萬漢字):約為「偏高」的下限,相鄰兩章同類都達到才列為提示。
# 這是起點值,依實際章節回頭調整;調整時只改這裡。
FLAG = {'連續否定': 4, '先否定後定義': 6, '公式化頓悟': 2, '三連同字起句': 6,
        '只見': 8, '忽然': 10, '竟': 14, '原來': 8, '彷彿': 10,
        '破折號': 10, '省略號': 6, '短段(非對白)': 60}
STOP = set('的了他她我你是在不有這那一個也就都說道把被和與又還要')


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def vol_key(path):
    for i, v in enumerate(VOLS):
        if f'/{v}/' in path.replace(os.sep, '/'):
            return i
    return len(VOLS)


def chapter_key(path):
    m = re.match(r'第(\d+)章', os.path.basename(path))
    return (vol_key(path), int(m.group(1)) if m else 0, path)


def collect(args):
    paths = []
    for a in args or ['正文']:
        if os.path.isdir(a):
            paths += glob.glob(os.path.join(a, '**', '第*章_*.md'), recursive=True)
        elif os.path.exists(a):
            paths.append(a)
    return sorted(set(paths), key=chapter_key)


def names():
    """角色名(掃描時先遮掉,免得人名被當成重複短語)。"""
    out = {'男主', '女主'}
    if os.path.isdir('角色/主要角色'):
        out |= {d for d in os.listdir('角色/主要角色') if os.path.isdir(f'角色/主要角色/{d}')}
    p = '正文/README.md'
    if os.path.exists(p):
        m = re.search(r'### 人物與稱呼\n(.*?)(?=\n### |\n## |\Z)', read(p), re.S)
        for b in re.findall(r'^- \*\*([^*]+)\*\*', m.group(1) if m else '', re.M):
            out |= {x for x in re.split(r'[\u3001,\uff0c]', b) if x}
    return sorted((n for n in out if len(n) >= 2), key=len, reverse=True)


def body(text):
    """去掉標題與引言行,只留正文段落。"""
    paras = []
    for line in text.split('\n'):
        s = line.strip()
        if not s or s.startswith('#') or s.startswith('>') or set(s) <= set('＊*-—'):
            continue
        paras.append(s)
    return paras


def is_dialogue(p):
    return p.startswith(('「', '『', '"', '“'))


def repeated_phrases(paras, nm, top=10):
    text = '\n'.join(paras)
    for n in nm:
        text = text.replace(n, '◇')
    clauses = re.split(r'[,\uff0c。!?\uff01\uff1f;\uff1b:\uff1a\u3001「」『』“”()\uff08\uff09\s]+|…+|—+', text)
    counts = {}
    for n in range(8, 3, -1):
        c = collections.Counter()
        for cl in clauses:
            if '◇' in cl:
                for seg in cl.split('◇'):
                    for i in range(len(seg) - n + 1):
                        c[seg[i:i + n]] += 1
            else:
                for i in range(len(cl) - n + 1):
                    c[cl[i:i + n]] += 1
        for k, v in c.items():
            if v >= (3 if n >= 6 else 4) and sum(ch in STOP for ch in k) / n < 0.5:
                counts[k] = v
    picked = []
    for k, v in sorted(counts.items(), key=lambda kv: (-len(kv[0]) * kv[1], kv[0])):
        if any(k in p and v <= pv for p, pv in picked):
            continue
        picked.append((k, v))
        if len(picked) >= top:
            break
    return picked


def analyze(path, nm):
    text = read(path)
    paras = body(text)
    joined = '\n'.join(paras)
    han = len(HAN.findall(joined)) or 1
    per = lambda n: n * 10000 / han
    cnt = collections.OrderedDict()
    examples = {}
    for k, rx in PATTERNS.items():
        ms = [joined[m.start():m.end() + 8].split('\n')[0] for m in rx.finditer(joined)]
        cnt[k] = len(ms)
        examples[k] = ms[:3]
    for w in WORDS:
        cnt[w] = joined.count(w)
    for k, s in MARKS.items():
        cnt[k] = joined.count(s)
    narr = [p for p in paras if not is_dialogue(p)]
    cnt['短段(非對白)'] = sum(1 for p in narr if len(HAN.findall(p)) <= 14)
    starts = collections.Counter(p[0] for p in paras if not is_dialogue(p))
    return {
        'path': path, 'han': han, 'paras': len(paras), 'cnt': cnt, 'ex': examples,
        'dens': {k: per(v) for k, v in cnt.items()},
        'rep': repeated_phrases(paras, nm),
        'starts': starts.most_common(3), 'narr': len(narr),
        'first': paras[0][:36] if paras else '', 'last': paras[-1][-36:] if paras else '',
    }


def label(path):
    p = path.replace(os.sep, '/')
    m = re.search(r'/?(序卷|第一部|第二部|第三部)/第(\d+)章', p)
    return f'{m.group(1)}·第{m.group(2)}章' if m else os.path.basename(p)


def main(argv):
    paths = collect(argv)
    if not paths:
        print('找不到章節檔(正文/ 下沒有 第N章_*.md)。')
        return 0
    nm = names()
    rs = [analyze(p, nm) for p in paths]
    keys = list(rs[0]['dens'])
    print('# 句式掃描(提示,非判決)\n')
    print('| 章 | 漢字 | 段 | ' + ' | '.join(keys) + ' |')
    print('|---|---|---|' + '---|' * len(keys))
    for r in rs:
        print(f"| {label(r['path'])} | {r['han']} | {r['paras']} | " + ' | '.join(f"{r['dens'][k]:.1f}" for k in keys) + ' |')
    print('\n> 數字為每萬漢字的出現次數(短段 = 十四字以內的非對白段);僅供對照,提示門檻在本檔的 FLAG。三連同字起句常抓到正常的列舉,看例句再判斷。')
    print('\n## 相鄰章比較')
    hits = 0
    for a, b in zip(rs, rs[1:]):
        same = [k for k in keys if FLAG.get(k) and a['dens'][k] >= FLAG[k] and b['dens'][k] >= FLAG[k]]
        if same:
            hits += 1
            print(f"- {label(a['path'])} → {label(b['path'])}:" + '、'.join(f"{k}({a['dens'][k]:.0f}→{b['dens'][k]:.0f})" for k in same) + ' 連續偏高')
    if not hits:
        print('- 沒有相鄰兩章同類同時偏高的項目。' if len(rs) > 1 else '- 只有一章,無相鄰比較。')
    for r in rs:
        print(f"\n## {label(r['path'])}")
        flagged = [k for k in keys if FLAG.get(k) and r['dens'][k] >= FLAG[k]]
        if flagged:
            print('- 單章偏高:' + '、'.join(f"{k}({r['cnt'][k]} 次)" for k in flagged))
        for k, ex in r['ex'].items():
            if ex:
                print(f'- {k}例句:' + ';'.join(f'「{e}」' for e in ex))
        if r['rep']:
            print('- 章內反覆短語(已遮人名):' + '、'.join(f'「{k}」×{v}' for k, v in r['rep']))
        if r['starts']:
            tot = r['narr'] or 1
            print('- 非對白段首字:' + '、'.join(f"「{c}」{n}/{tot}" for c, n in r['starts']))
        print(f"- 首段:{r['first']}…")
        print(f"- 末段:…{r['last']}")
    print('\n提示只是請你重讀這幾處。有真正的對照、真的新增資訊時,照用。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
