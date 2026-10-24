#!/usr/bin/env python3
"""讀者模擬測試包(劇情基準 I 組)。把「只讀到某一點的讀者」需要的資料組成一份可交給全新 session 的 Markdown。

用法:
  python3 工具/讀者測試包.py 取樣                          # 列出建議的測試切點與轉折事件(確定性,可重現)
  python3 工具/讀者測試包.py 預測 第二部 12 [--k 3] [--out F]   # 預測測試包:讀到第 12 章結束,預測接下來的事
  python3 工具/讀者測試包.py 答案 第二部 12 [--k 3] [--out F]   # 該切點之後實際發生的事與讀者此時應已感知的伏筆(給評分者)
  python3 工具/讀者測試包.py 線索 P2-141 [--out F]            # 線索測試包:給出謎底,請找出前文能支持它的線索
  python3 工具/讀者測試包.py 掃描                          # 轉折(反轉、揭露)事件的鋪墊掃描(純計數,不需要 LLM)

只讀、不改任何專案檔案;輸出不進版本庫(放專案之外或暫存區)。流程、評分規則與偏差見 設計規範/讀者測試.md。

「讀者可見」的定義:只含該切點以前、有章節的事件(演出,以及在該章被提及的事件)的名稱,最近兩章附簡述。
不給:背景事件(章號 0)、標籤、伏筆登記簿、秘密知情矩陣、吸引力分析、章節大綱的「本章目標」,以及切點之後的任何內容。
注意:事件名稱是設計者寫的,可能比讀者實際讀到的資訊更多;因此「預測命中」的證據力較弱,「預測落空且事後合理」的證據力較強。
"""
import os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 劇情量化 as Q

LEADS = Q.LEADS
TWIST_TAGS = ('反轉', '揭露')
HINT_TAGS = ('伏筆', '懸念', '宿命')
HINT_WINDOW = 8        # 掃描時,往前看幾章有沒有帶暗示標籤的事件
DEFAULT_K = 3


# ---------- 資料 ----------

def load():
    tl, ev, ci, pos = Q.load_all()
    desc = {}
    for v in Q.VOLS:
        t = Q.read(f'故事線/{v}/事件描述.md')
        for m in re.finditer(r'### ([A-Z0-9]+-\d+) ([^\n]+)\n(.*?)(?=\n### |\Z)', t, re.S):
            d = re.search(r'- \*\*描述\*\*:(.*)', m.group(3))
            desc[m.group(1)] = d.group(1).strip() if d else ''
    return tl, ev, ci, pos, desc


def ordered(tl):
    """全書有章節的事件,依 (全書章序, 卷內序號) 排序。"""
    out = []
    for v in Q.VOLS:
        for r in tl[v]:
            if r['ch'] > 0:
                out.append(dict(r, g=Q.gidx(v, r['ch'])))
    return sorted(out, key=lambda r: (r['g'], Q.VOLS.index(r['vol']), r['seq']))


def key_of(r):
    return (r['g'], Q.VOLS.index(r['vol']), r['seq'])


def expand_ids(text):
    """取出文字中的事件 ID,並展開「A 至 B」的範圍(限同一卷前綴)。"""
    ids = []
    for m in re.finditer(r'((?:PRO|P[123])-)(\d+) 至 (?:(?:PRO|P[123])-)?(\d+)', text):
        a, b = int(m.group(2)), int(m.group(3))
        if 0 <= b - a < 200:
            ids += [f'{m.group(1)}{n:03d}' for n in range(a, b + 1)]
    ids += Q.ID.findall(text)
    return list(dict.fromkeys(ids))


def registry():
    rows = []
    for c in Q.table(Q.read('狀態/伏筆登記簿.md')):
        if len(c) >= 5 and re.fullmatch(r'THR-\d+', c[0]):
            rows.append({'id': c[0], 'title': c[1], 'setup': expand_ids(c[2]), 'payoff': expand_ids(c[3]), 'status': c[4]})
    return rows


def cut_of(arg_vol, arg_ch, ci):
    if arg_vol not in Q.VOLS:
        sys.exit(f'卷名須為 {"、".join(Q.VOLS)}')
    n = int(arg_ch)
    if n not in ci[arg_vol]:
        sys.exit(f'{arg_vol} 沒有第 {n} 章')
    return Q.gidx(arg_vol, n)


def label(g):
    for v in reversed(Q.VOLS):
        if g > Q.OFF[v]:
            return f'{v}第 {g - Q.OFF[v]} 章'
    return str(g)


# ---------- 組包 ----------

def read_section(evs, ci, desc, cut, with_desc_from):
    lines, cur = [], None
    for r in evs:
        if r['g'] > cut:
            break
        head = (r['vol'], r['ch'])
        if head != cur:
            cur = head
            title = ci[r['vol']].get(r['ch'], {}).get('title', '')
            lines += ['', f"### {r['vol']} 第 {r['ch']} 章 {title}".rstrip()]
        mark = '(被提及)' if r['kind'] == '提及' else ''
        lines.append(f"- {r['id']} {r['name']}{mark}")
        if r['g'] >= with_desc_from and desc.get(r['id']):
            lines.append(f"  - 簡述:{desc[r['id']]}")
    return '\n'.join(lines).lstrip('\n')


def predict_pack(vol, n, k):
    tl, ev, ci, pos, desc = load()
    cut = cut_of(vol, n, ci)
    evs = ordered(tl)
    body = read_section(evs, ci, desc, cut, cut - 1)
    return f"""# 讀者預測測試包(讀到 {vol} 第 {n} 章結束)

你是這部長篇武俠小說的**第一次閱讀者**。下面是你「已經讀過」的內容:依章節順序的事件名稱,最近兩章附簡述。
你對這個世界、人物與後面的劇情一無所知。**只能使用本包的內容與你對武俠類型的一般理解**;不要讀取專案資料夾裡的其他檔案,不要搜尋。

## 任務

1. 預測接下來會發生的 {k} 個事件(依發生順序)。每個一句話:誰、做了什麼、結果如何。每個標信心:高(幾乎確定)、中、低。
2. 預測下一章結束時故事「停在什麼局面」,一至兩句。
3. 列出你現在**心中懸著的問題**(至多 8 條):你覺得作者埋下了、還沒交代的事。每條註明是哪個事件讓你這麼想。
4. 指出讀到現在**最想跳過或最覺得拖沓**的一段(章號與原因);沒有就寫「沒有」。
5. 不確定就標低信心,寫不出就留空,不要為了顯得準而硬湊;也不要迎合作者。

## 輸出格式

```
## 預測事件
1. [信心] 一句話
2. [信心] 一句話
{'...' if k > 2 else ''}
## 下一章結束的局面
...
## 懸著的問題
1. 問題(因 事件ID)
## 最想跳過的段落
...
```

## 你已讀過的內容

{body}
"""


def answer_pack(vol, n, k):
    tl, ev, ci, pos, desc = load()
    cut = cut_of(vol, n, ci)
    evs = ordered(tl)
    cut_key = max((key_of(r) for r in evs if r['g'] <= cut), default=(0, 0, 0))
    nxt = [r for r in evs if key_of(r) > cut_key and r['kind'] == '演出'][:k]
    lines = [f'# 預測測試答案(切點:{vol} 第 {n} 章結束;K={k})', '',
             '> 給評分者。評分者須是另一個全新的 session,同時拿到預測者的輸出。規則見 設計規範/讀者測試.md。', '',
             '## 實際發生的下一批演出事件']
    for i, r in enumerate(nxt, 1):
        lines += [f"{i}. {r['id']}({r['vol']}第 {r['ch']} 章){r['name']}", f"   - 簡述:{desc.get(r['id'], '')}"]
    if nxt:
        last = nxt[-1]
        ch_events = [x for x in evs if x['g'] == nxt[0]['g'] and x['kind'] == '演出']
        end = ch_events[-1] if ch_events else last
        lines += ['', f"## 下一章({label(nxt[0]['g'])})結束時的局面", f"- 最後一個演出事件:{end['id']} {end['name']}"]
    lines += ['', '## 此時讀者應已感知的伏筆(登記簿中設置點已在切點以前、回收點還在切點之後者)',
              '> 用來計算「懸著的問題」的對應率:預測者列出的問題,與下表哪幾條實質對應。']
    reg = registry()
    seen = {r['id']: r for r in evs}
    n_pl = 0
    for r in reg:
        setups = [s for s in r['setup'] if s in seen and seen[s]['g'] <= cut]
        payoffs = [p for p in r['payoff'] if p in seen]
        if setups and payoffs and min(seen[p]['g'] for p in payoffs) > cut:
            n_pl += 1
            lines.append(f"- {r['id']} {r['title']}(設置 {setups[0]},回收 {payoffs[0]})")
    if not n_pl:
        lines.append('- (無)')
    return '\n'.join(lines) + '\n'


def clue_pack(eid):
    tl, ev, ci, pos, desc = load()
    evs = ordered(tl)
    target = next((r for r in evs if r['id'] == eid), None)
    if not target:
        sys.exit(f'找不到有章節的事件 {eid}(背景事件不能當線索測試的目標)')
    tkey = key_of(target)
    before = [r for r in evs if key_of(r) < tkey]
    body = read_section(before, ci, desc, target['g'], 0)
    return f"""# 線索測試包({eid}:{target['name']})

下面先給你**謎底**,再給這個謎底「之前」讀者已讀過的全部內容。請你判斷:一位專心的讀者,**事前**能不能由前文推測出這個轉折?

只能使用本包的內容;不要讀取專案資料夾裡的其他檔案。

## 謎底

- 事件:{eid} {target['name']}({target['vol']}第 {target['ch']} 章)
- 簡述:{desc.get(eid, '')}

## 任務

1. 找出前文中能支持這個謎底的線索。每條寫:事件 ID、它提供的資訊、強度(強:明示了一半以上;中:能聯想;弱:要事後才看得出)。
2. 找出前文中與謎底**矛盾**或誤導過頭的事件(讀者會因此得出相反結論,事後覺得被騙)。沒有就寫「無」。
3. 下結論,三選一:
   - 公平:專心的讀者能推到八成,揭曉時覺得「原來如此」而不是「憑空冒出」;
   - 勉強:線索偏弱或偏少,多數讀者會猜不到,且事後也不太會翻回去找;
   - 突兀:前文幾乎沒有線索,或有矛盾,揭曉等於憑空添加。
4. 若結論不是「公平」,指出補強最省事的位置(哪個既有事件可加一筆),只給位置,不改寫內容。

## 輸出格式

```
## 線索
1. [強/中/弱] 事件ID:提供了什麼
## 矛盾或誤導
...
## 結論
公平/勉強/突兀:一句理由
## 補強位置
...
```

## 謎底之前的內容(讀者已讀)

{body}
"""


# ---------- 掃描與取樣 ----------

def twist_events(tl):
    return [r for r in ordered(tl) if r['kind'] == '演出' and set(r['tags']) & set(TWIST_TAGS)]


def scan():
    tl, ev, ci, pos, desc = load()
    evs = ordered(tl)
    byid = {r['id']: r for r in evs}
    reg = registry()
    out = ['轉折事件(標籤帶反轉、揭露的演出事件)的鋪墊掃描', '',
           '| 事件 | 章 | 事件名稱 | 登記伏筆 | 最近設置距離(章) | 近 %d 章同角色的暗示事件 |' % HINT_WINDOW, '|---|---|---|---|---|---|']
    zero, total = [], 0
    for r in twist_events(tl):
        total += 1
        linked = [x for x in reg if r['id'] in x['payoff']]
        dist = []
        for x in linked:
            ds = [r['g'] - byid[s]['g'] for s in x['setup'] if s in byid and byid[s]['g'] <= r['g']]
            if ds:
                dist.append(min(ds))
        chars = set(ev[r['vol']].get(r['id'], {}).get('chars', [])) - set(LEADS) or set(LEADS)
        hints = [x for x in evs if r['g'] - HINT_WINDOW <= x['g'] <= r['g'] and key_of(x) < key_of(r)
                 and set(x['tags']) & set(HINT_TAGS)
                 and chars & set(ev[x['vol']].get(x['id'], {}).get('chars', []))]
        if not linked:
            zero.append((r, len(hints)))
        out.append(f"| {r['id']} | {r['vol']}第 {r['ch']} 章 | {r['name']} | {len(linked)} | "
                   f"{min(dist) if dist else '—'} | {len(hints)} |")
    out += ['', f'轉折事件共 {total} 個;登記簿沒有對應伏筆的 {len(zero)} 個。',
            '登記簿以外的鋪墊(角色塑造、前文的小動作)這個計數看不到,「近 %d 章同角色的暗示事件」只是粗略的補充。' % HINT_WINDOW,
            '兩欄都是 0 或很小的事件,優先做線索測試(`讀者測試包.py 線索 事件ID`),看前文實際有沒有鋪墊。']
    return '\n'.join(out) + '\n'


def spaced(items, n):
    if not items or n <= 0:
        return []
    n = min(n, len(items))
    return [items[int((i + 0.5) * len(items) / n)] for i in range(n)]


def sample():
    tl, ev, ci, pos, desc = load()
    lines = ['建議的測試切點與轉折事件(確定性取樣:每卷等距挑選,重跑結果相同)', '', '預測測試切點(每卷 4 個,用 `預測` 與 `答案`):']
    for v in Q.VOLS[1:]:
        chs = sorted(ci[v])
        pool = [c for c in chs if 3 <= c <= chs[-1] - 1]
        lines.append(f"  {v}:" + '、'.join(f'第 {c} 章' for c in spaced(pool, 4)))
    lines += ['', '線索測試事件(每卷 3 個轉折,用 `線索`):']
    for v in Q.VOLS[1:]:
        pool = [r for r in twist_events(tl) if r['vol'] == v]
        lines.append(f"  {v}:" + '、'.join(f"{r['id']}(第 {r['ch']} 章 {r['name'][:14]})" for r in spaced(pool, 3)))
    lines += ['', '每個測試用一個全新的 session;預測者與評分者不可是同一個 session。結果記到 設計規範/讀者測試記錄.md。']
    return '\n'.join(lines) + '\n'


def main(argv):
    out = None
    if '--out' in argv:
        i = argv.index('--out')
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    k = DEFAULT_K
    if '--k' in argv:
        i = argv.index('--k')
        k = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        return 1
    mode, args = argv[0], argv[1:]
    if mode == '預測' and len(args) == 2:
        text = predict_pack(args[0], args[1], k)
    elif mode == '答案' and len(args) == 2:
        text = answer_pack(args[0], args[1], k)
    elif mode == '線索' and len(args) == 1:
        text = clue_pack(args[0])
    elif mode == '掃描':
        text = scan()
    elif mode == '取樣':
        text = sample()
    else:
        print(__doc__)
        return 1
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'已寫入 {out}({len(text)} 字)')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
