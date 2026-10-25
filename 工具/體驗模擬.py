#!/usr/bin/env python3
"""體驗模擬(劇情基準 K 組):把劇情當成一串刺激,推估體驗者在每一章的狀態。只讀,不改任何檔案。

用法:
  python3 工具/體驗模擬.py                    # 完整報告印到標準輸出
  python3 工具/體驗模擬.py --out 檔案.md       # 寫成檔案
  python3 工具/體驗模擬.py --csv 檔案.csv      # 另存逐章數列(供畫圖)
  python3 工具/體驗模擬.py --draws 100         # 改蒙地卡羅抽樣次數(預設讀 設計規範/體驗參數.md)
  python3 工具/體驗模擬.py --自測              # 用已知答案的小資料檢查各函式

它量的是「劇情資料的結構性前因」,不是品質:
  K1 讀者知情(戲劇反諷、謎團庫存)   K2 開放問題庫存      K3 記憶保留(伏筆回收時還記得嗎)
  K4 事件索引轉換負荷               K5 效價與喚起軌跡    K6 損失的情感衝擊
  K7 讀者模擬器(蒙地卡羅;只信穩健的結論)
全部參數是假說,見 設計規範/體驗參數.md;怎麼檢驗這些量有沒有鑑別力,見 工具/變異測試.py。
研究依據與限制見 設計規範/體驗量化研究.md。
"""
import copy, math, os, random, re, statistics, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 劇情量化 as Q
import 代價帳 as L
import 讀者測試包 as R

LEADS = Q.LEADS
WARM = ('溫情', '日常', '幽默', '誓約', '成長')
PARAM_FILE = '設計規範/體驗參數.md'
READER_FILE = '狀態/讀者知情.md'
SPARK = '▁▂▃▄▅▆▇█'


# ---------- 參數 ----------

def _section(text, name):
    m = re.search(r'## ' + re.escape(name) + r'\n(.*?)(?=\n## |\Z)', text, re.S)
    return Q.table(m.group(1)) if m else []


def _num(s):
    try:
        return float(s)
    except ValueError:
        return None


def load_params():
    text = Q.read(PARAM_FILE)
    P = {'tag': {}, 'ret': {}, 'load': {}, 'loss': {}, 'sim': {}, 'mc': {}}
    for c in _section(text, '標籤的效價與喚起'):
        if len(c) >= 3 and _num(c[1]) is not None:
            P['tag'][c[0]] = (_num(c[1]), _num(c[2]))
    for key, name in (('ret', '記憶保留'), ('load', '事件索引轉換負荷'), ('loss', '損失衝擊'), ('mc', '蒙地卡羅設定')):
        for c in _section(text, name):
            if len(c) >= 2 and _num(c[1]) is not None and not c[0].startswith('-'):
                P[key][c[0]] = _num(c[1])
    for c in _section(text, '讀者模擬器'):
        if len(c) >= 3 and _num(c[1]) is not None and _num(c[2]) is not None:
            P['sim'][c[0]] = (_num(c[1]), _num(c[2]))
    return P


# ---------- 世界(可複製、可被擾動) ----------

def months_of(rel):
    """相對時間字串 → 月數;無法換算回傳 None。"""
    if '初遇夜' in rel:
        return 0.0
    m = re.match(r'初遇後 (\d+) 年(?: (\d+) 個月)?', rel)
    if m:
        return 12.0 * int(m.group(1)) + int(m.group(2) or 0)
    m = re.match(r'初遇後 (\d+) 個月', rel)
    if m:
        return float(m.group(1))
    m = re.match(r'初遇後 (\d+) 日', rel)
    if m:
        return int(m.group(1)) / 30.0
    return None


def load_threads():
    out = []
    for c in Q.table(Q.read('狀態/伏筆登記簿.md')):
        if len(c) >= 6 and re.fullmatch(r'THR-\d+', c[0]):
            parts = c[2].split('呼應:')
            out.append({'id': c[0], 'title': c[1], 'setup': R.expand_ids(parts[0]),
                        'echo': R.expand_ids(parts[1]) if len(parts) > 1 else [],
                        'payoff': R.expand_ids(c[3]), 'secrets': re.findall(r'SEC-\d+', c[5])})
    return out


def load_secrets():
    """狀態/讀者知情.md → [{id, title, hint, known, lead_m, lead_f}],事件 ID 或 None。檔案不存在則回傳 []。"""
    rows = []
    for c in Q.table(Q.read(READER_FILE)):
        if len(c) >= 6 and re.fullmatch(r'SEC-\d+', c[0]):
            ids = [(Q.ID.search(x).group(0) if Q.ID.search(x) else None) for x in c[2:6]]
            rows.append({'id': c[0], 'title': c[1], 'hint': ids[0], 'known': ids[1], 'lead_m': ids[2], 'lead_f': ids[3]})
    return rows


def load_world():
    tl, ev, ci, pos = Q.load_all()
    events, bg = [], {}
    for v in Q.VOLS:
        for r in tl[v]:
            e = ev[v].get(r['id'], {'chars': [], 'scenes': [], 'facs': []})
            if r['ch'] > 0:
                events.append({'id': r['id'], 'vol': v, 'ch': r['ch'], 'g': Q.gidx(v, r['ch']), 'seq': r['seq'],
                               'rel': r['rel'], 'months': months_of(r['rel']), 'tags': list(r['tags']), 'kind': r['kind'],
                               'name': r['name'], 'chars': list(e['chars']), 'scenes': [s for s, _ in e['scenes']]})
            else:
                bg[r['id']] = Q.gidx(v, 0)
    events.sort(key=lambda r: (r['g'], Q.VOLS.index(r['vol']), r['seq']))
    n = sum(Q.chapter_count(v) for v in Q.VOLS)
    return {'events': events, 'bg': bg, 'n': n, 'threads': load_threads(), 'secrets': load_secrets(),
            'ledger': L.load_ledger(), 'titles': {(v, k): c['title'] for v in Q.VOLS for k, c in ci[v].items()}}


def gpos(w):
    d = dict(w['bg'])
    for e in w['events']:
        d[e['id']] = e['g']
    return d


def chap_label(w, g):
    for v in reversed(Q.VOLS):
        if g > Q.OFF[v]:
            return f'{v}第 {g - Q.OFF[v]} 章'
    return f'第 {g} 章'


def chap_title(w, g):
    for v in reversed(Q.VOLS):
        if g > Q.OFF[v]:
            return w['titles'].get((v, g - Q.OFF[v]), '')
    return ''


def vol_ranges(w):
    out = {}
    for e in w['events']:
        a, b = out.get(e['vol'], (e['g'], e['g']))
        out[e['vol']] = (min(a, e['g']), max(b, e['g']))
    return out


# ---------- 小工具 ----------

def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def spark(xs):
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-12:
        return SPARK[0] * len(xs)
    return ''.join(SPARK[min(7, int((x - lo) / (hi - lo) * 8))] for x in xs)


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a, b):
    ma, mb = mean(a), mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if sa < 1e-12 or sb < 1e-12:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def longest_run(flags):
    """flags:每章是否成立(索引 0 對應第 1 章)。回傳 (長度, 起章, 迄章),章號從 1 起。"""
    best, run, start = (0, 0, 0), 0, 0
    for i, f in enumerate(flags):
        if f:
            if run == 0:
                start = i + 1
            run += 1
            if run > best[0]:
                best = (run, start, i + 1)
        else:
            run = 0
    return best


def smooth(xs, win):
    half = win // 2
    return [mean(xs[max(0, i - half):i + half + 1]) for i in range(len(xs))]


def resample(xs, m):
    if len(xs) == 1:
        return [xs[0]] * m
    out = []
    for k in range(m):
        t = k * (len(xs) - 1) / (m - 1)
        i = min(int(t), len(xs) - 2)
        out.append(xs[i] + (xs[i + 1] - xs[i]) * (t - i))
    return out


def dfa_alpha(x, smin=4, points=10):
    """去趨勢波動分析(DFA-1)的標度指數;白雜訊約 0.5,有長程相關者較大。"""
    n = len(x)
    if n < 32:
        return None
    m = mean(x)
    y, s = [], 0.0
    for v in x:
        s += v - m
        y.append(s)
    hi = math.log(max(smin + 1, n // 4))
    scales = sorted({int(round(math.exp(math.log(smin) + (hi - math.log(smin)) * t / (points - 1)))) for t in range(points)})
    pts = []
    for sc in scales:
        nb = n // sc
        if nb < 2:
            continue
        tot = 0.0
        xm = (sc - 1) / 2
        sxx = sum((i - xm) ** 2 for i in range(sc))
        for b in range(nb):
            seg = y[b * sc:(b + 1) * sc]
            ym = mean(seg)
            a = sum((i - xm) * (seg[i] - ym) for i in range(sc)) / sxx
            tot += sum((seg[i] - (ym + a * (i - xm))) ** 2 for i in range(sc))
        f = math.sqrt(tot / (nb * sc))
        if f > 0:
            pts.append((math.log(sc), math.log(f)))
    if len(pts) < 3:
        return None
    mx, my = mean(p[0] for p in pts), mean(p[1] for p in pts)
    return sum((a - mx) * (b - my) for a, b in pts) / sum((a - mx) ** 2 for a, _ in pts)


# ---------- K1/K2 讀者知情與開放問題 ----------

def touches_of(t, G):
    return sorted(G[i] for i in t['setup'] + t['echo'] if i in G)


def thread_intervals(w):
    """每條伏筆:{'t': 伏筆, 'start': 開放起章, 'pay': 回收章, 'touch': 接觸點章序}。無設置點或無回收者略過。"""
    G = gpos(w)
    out = []
    for t in w['threads']:
        tc = touches_of(t, G)
        pays = [G[i] for i in t['payoff'] if i in G]
        if not tc or not pays:
            continue
        out.append({'t': t, 'start': max(1, tc[0]), 'pay': max(1, min(pays)), 'touch': [max(1, x) for x in tc]})
    return out


def secret_intervals(w):
    G = gpos(w)
    out = []
    for s in w['secrets']:
        g = {k: (max(1, G[s[k]]) if s[k] in G else None) for k in ('hint', 'known', 'lead_m', 'lead_f')}
        out.append(dict(s, **{'g_' + k: v for k, v in g.items()}))
    return out


def retention(c, touches, S0, beta):
    """第 c 章時,依接觸點(含設置與呼應)算的保留機率。"""
    past = [x for x in touches if x <= c]
    if not past:
        return 0.0
    return math.exp(-(c - past[-1]) / (S0 * (1 + beta * (len(past) - 1))))


def open_questions(w, P):
    """逐章:Q(開放問題數)、Qeff(保留加權)、M(謎團)、DI(戲劇反諷,男/女/任一)。索引 1..n。"""
    n = w['n']
    S0, beta = P['ret']['S0'], P['ret']['β']
    Qn, Qe, M = [0] * (n + 1), [0.0] * (n + 1), [0] * (n + 1)
    DI = {'男主': [0] * (n + 1), '女主': [0] * (n + 1), '任一': [0] * (n + 1)}
    covered = {s for t in w['threads'] for s in t['secrets']}
    ti = thread_intervals(w)
    for it in ti:
        for c in range(it['start'], min(it['pay'], n + 1)):
            Qn[c] += 1
            Qe[c] += retention(c, it['touch'], S0, beta)
    for s in secret_intervals(w):
        if s['g_known'] is None:
            continue
        if s['g_hint'] is not None and s['g_hint'] < s['g_known']:
            for c in range(s['g_hint'], s['g_known']):
                M[c] += 1
                if s['id'] not in covered:
                    Qn[c] += 1
                    Qe[c] += retention(c, [s['g_hint']], S0, beta)
        for who, key in (('男主', 'g_lead_m'), ('女主', 'g_lead_f')):
            end = s[key] if s[key] is not None else n + 1
            for c in range(s['g_known'], min(end, n + 1)):
                DI[who][c] += 1
        for c in range(s['g_known'], n + 1):
            lm = s['g_lead_m'] if s['g_lead_m'] is not None else n + 1
            lf = s['g_lead_f'] if s['g_lead_f'] is not None else n + 1
            if c < max(lm, lf):
                DI['任一'][c] += 1
    return {'Q': Qn, 'Qeff': Qe, 'M': M, 'DI': DI, 'threads': len(ti)}


# ---------- K3 記憶保留 ----------

def thread_retention(w, P, S0=None):
    S0 = S0 or P['ret']['S0']
    beta = P['ret']['β']
    rows = []
    for it in thread_intervals(w):
        before = [x for x in it['touch'] if x <= it['pay']]
        r = retention(it['pay'], before, S0, beta)
        rows.append({'id': it['t']['id'], 'title': it['t']['title'], 'pay': it['pay'], 'last': before[-1] if before else None,
                     'n': len(before), 'R': r, 'gap': it['pay'] - (before[-1] if before else it['pay'])})
    return rows


def character_returns(w, P):
    app = {}
    for e in w['events']:
        if e['kind'] != '演出':
            continue
        for c in e['chars']:
            app.setdefault(c, set()).add(e['g'])
    S0c, beta = P['ret']['角色 S0'], P['ret']['β']
    rows = []
    for c, gs in app.items():
        gs = sorted(gs)
        for i in range(1, len(gs)):
            gap = gs[i] - gs[i - 1]
            rows.append({'who': c, 'from': gs[i - 1], 'to': gs[i], 'gap': gap, 'n': i,
                         'R': math.exp(-gap / (S0c * (1 + beta * i)))})
    return rows, {c: len(g) for c, g in app.items()}


# ---------- K4 事件索引轉換負荷 ----------

def load_profile(w, P):
    p = P['load']
    n = w['n']
    stage = [e for e in w['events'] if e['kind'] == '演出']
    first_thread = {}
    for t in w['threads']:
        ids = [i for i in t['setup'] if i in gpos(w)]
        if ids:
            first_thread.setdefault(min(ids, key=lambda i: gpos(w)[i]), []).append(t['id'])
    seen_c, seen_s = set(), set()
    Lc = [0.0] * (n + 1)
    comp = [dict(time=0.0, space=0.0, lead=0.0, cast=0.0, new=0.0) for _ in range(n + 1)]
    prev = None
    unparsed = 0
    for e in stage:
        c = e['g']
        new = sum(1 for x in set(e['chars']) - seen_c if x not in LEADS) * p['新角色首次登場'] \
            + sum(1 for s in set(e['scenes']) - seen_s) * p['新場景首次出現'] + len(first_thread.get(e['id'], [])) * p['新伏筆設置']
        seen_c |= set(e['chars'])
        seen_s |= set(e['scenes'])
        comp[c]['new'] += new
        if e['months'] is None:
            unparsed += 1
        if prev is not None:
            if e['months'] is not None and prev['months'] is not None:
                d = e['months'] - prev['months']
                tm = 0.0
                if d < 0:
                    tm = p['時間倒退']
                else:
                    tm = (p['時間跳躍 ≥ 3 個月'] if d >= 3 else 0) + (p['時間跳躍 ≥ 12 個月'] if d >= 12 else 0)
                comp[c]['time'] += tm
            if e['scenes'] and prev['scenes'] and not (set(e['scenes']) & set(prev['scenes'])):
                comp[c]['space'] += p['空間轉換']
            if tuple(sorted(set(e['chars']) & set(LEADS))) != tuple(sorted(set(prev['chars']) & set(LEADS))):
                comp[c]['lead'] += p['主角轉換']
            a, b = set(e['chars']), set(prev['chars'])
            if a | b:
                comp[c]['cast'] += p['配角更替'] * (1 - len(a & b) / len(a | b))
        prev = e
    for c in range(1, n + 1):
        Lc[c] = sum(comp[c].values())
    return {'L': Lc, 'comp': comp, 'unparsed': unparsed, 'stage': len(stage)}


# ---------- K5 效價與喚起 ----------

def event_va(e, P):
    vs = [P['tag'][t] for t in e['tags'] if t in P['tag']]
    if not vs:
        return 0.0, 0.1
    val = mean(v for v, _ in vs)
    aro = 0.6 * max(a for _, a in vs) + 0.4 * mean(a for _, a in vs)
    return val, aro


def arousal_profile(w, P):
    n = w['n']
    per = [[] for _ in range(n + 1)]
    ev_series = []
    for e in w['events']:
        if e['kind'] != '演出':
            continue
        v, a = event_va(e, P)
        per[e['g']].append((v, a))
        ev_series.append((e['g'], v, a))
    val, aro = [0.0] * (n + 1), [0.0] * (n + 1)
    for c in range(1, n + 1):
        if per[c]:
            val[c] = mean(v for v, _ in per[c])
            aro[c] = 0.5 * mean(a for _, a in per[c]) + 0.5 * max(a for _, a in per[c])
        else:
            val[c], aro[c] = 0.0, 0.1
    return {'val': val, 'aro': aro, 'events': ev_series}


SHAPES = {
    '一路上升(rags to riches)': lambda x: x,
    '一路下降(riches to rags)': lambda x: -x,
    '先降後升(man in a hole)': lambda x: -math.sin(math.pi * x),
    '先升後降(Icarus)': lambda x: math.sin(math.pi * x),
    '升降升(Cinderella)': lambda x: math.sin(2 * math.pi * x),
    '降升降(Oedipus)': lambda x: -math.sin(2 * math.pi * x),
}


def shape_fit(series):
    arc = resample(smooth(series, max(3, len(series) // 8)), 50)
    xs = [i / 49 for i in range(50)]
    return sorted(((pearson(arc, [f(x) for x in xs]), name) for name, f in SHAPES.items()), reverse=True)


def dfa_with_null(x, seed, reps=200):
    a = dfa_alpha(x)
    if a is None:
        return None, None, None
    rng = random.Random(seed)
    nulls = []
    y = list(x)
    for _ in range(reps):
        rng.shuffle(y)
        b = dfa_alpha(y)
        if b is not None:
            nulls.append(b)
    mu, sd = mean(nulls), (statistics.pstdev(nulls) if len(nulls) > 1 else 0)
    return a, mu, ((a - mu) / sd if sd > 1e-9 else 0.0)


# ---------- K6 損失衝擊 ----------

def attachment(w, P, who, g_ev):
    """到事件章為止,讀者對角色 who 的依附度。w 中的出場事件按章序累計,同場有溫情類標籤者加權。"""
    k, warm = P['loss']['依附速率 k'], P['loss']['溫情加權']
    tot = 0.0
    for e in w['events']:
        if e['kind'] != '演出' or e['g'] > g_ev:
            continue
        if who in e['chars']:
            tot += warm if set(e['tags']) & set(WARM) else 1.0
    return 1 - math.exp(-k * tot)


def loss_profile(w, P, rows=None):
    p = P['loss']
    n = w['n']
    G = gpos(w)
    rows = w['ledger'] if rows is None else rows
    dead_at = {}      # 章序 → 該章死去的具名非主角
    for r in rows:
        if r['cat'] == '生命' and r['who'] not in LEADS and r['id'] in G and G[r['id']] >= 1:
            dead_at.setdefault(G[r['id']], []).append(r['who'])
    imp = [0.0] * (n + 1)
    items = []
    for r in rows:
        if r['who'] not in LEADS or r['id'] not in G or G[r['id']] < 1:
            continue
        g = G[r['id']]
        base = p.get(r['cat'], 0.5)
        if r['cat'] == '亡故':
            ds = list(dict.fromkeys(dead_at.get(g, []) + dead_at.get(g - 1, [])))   # 同章,或前一章(P3-083 殞命、P3-084 哀悼)
            att = max((attachment(w, P, d, g) for d in ds), default=p['未具名受害者依附度'])
            who_lost = '、'.join(ds) if ds else '(未具名)'
        else:
            att, who_lost = 1.0, ''
        v = base * att * p.get(r['rev'], 0.5)
        imp[g] += v
        items.append({'id': r['id'], 'g': g, 'who': r['who'], 'cat': r['cat'], 'rev': r['rev'], 'lost': who_lost,
                      'att': att, 'impact': v, 'loss': r['loss']})
    return {'I': imp, 'items': items}


# ---------- K7 讀者模擬器 ----------

def simulate(series, prm):
    """series: Qeff, aro, load_ex, imp;prm:一組參數。回傳逐章投入 E 與組成。"""
    n = len(series['aro']) - 1
    E, parts = [0.0] * (n + 1), [None] * (n + 1)
    fat = bore = 0.0
    adapt = None
    mu, bw = prm['喚起甜蜜點'], prm['喚起帶寬']
    for c in range(1, n + 1):
        cur = 1 - math.exp(-series['Qeff'][c] / prm['q0'])
        a = series['aro'][c]
        adapt = a if adapt is None else adapt
        sig = lambda x: 1 / (1 + math.exp(-x))
        # 喚起的貢獻一部分看絕對強度,一部分看高出讀者已適應水準的部分(只計高出,不計低於):長期同一強度會習慣,安靜之後的高潮才格外有力
        arc = (1 - prm['對比比重']) * sig((a - mu) / (bw / 2)) + prm['對比比重'] * min(1.0, max(0.0, a - adapt) / bw)
        adapt = prm['適應速率'] * adapt + (1 - prm['適應速率']) * a
        fat = prm['疲勞衰減'] * fat + max(0.0, a - prm['疲勞起點'])
        bore = prm['疲勞衰減'] * bore + max(0.0, prm['無聊起點'] - a)
        loss = 1 - math.exp(-series['imp'][c])
        parts[c] = {'好奇': prm['好奇權重'] * cur, '喚起': prm['喚起權重'] * arc, '損失': prm['損失權重'] * loss,
                    '負荷': -prm['負荷權重'] * series['load_ex'][c], '疲勞': -prm['疲勞權重'] * min(1.5, fat), '無聊': -prm['無聊權重'] * min(1.5, bore)}
        E[c] = sum(parts[c].values())
    return E, parts


def sim_series(w, P):
    oq = open_questions(w, P)
    ap = arousal_profile(w, P)
    lp = load_profile(w, P)
    ls = loss_profile(w, P)
    n = w['n']
    lv = [x for x in lp['L'][1:] if x > 0]
    med = statistics.median(lv) if lv else 1.0
    sd = statistics.pstdev(lv) if len(lv) > 1 else 1.0
    load_ex = [0.0] + [min(1.0, max(0.0, ((lp['L'][c] - med) / (sd or 1.0)) - 0.5) / 2) for c in range(1, n + 1)]   # 0 到 1:超過基準 0.5 個標準差起算,2.5 個標準差封頂
    return {'Qeff': oq['Qeff'], 'aro': ap['aro'], 'load_ex': load_ex, 'imp': ls['I']}, oq, ap, lp, ls


def monte_carlo(series, P, draws=None, seed=None):
    rng = random.Random(seed if seed is not None else int(P['mc']['種子']))
    draws = int(draws or P['mc']['抽樣次數'])
    n = len(series['aro']) - 1
    keys = list(P['sim'])
    runs = []
    for _ in range(draws):
        prm = {k: rng.uniform(*P['sim'][k]) for k in keys}
        E, parts = simulate(series, prm)
        h0, s = prm['基礎流失'], prm['流失敏感度']
        ref = 0.5 * prm['好奇權重'] + 0.5 * prm['喚起權重']      # 「普通章」的投入:好奇與喚起各半、沒有損失也沒有扣分
        S, surv = 1.0, [1.0]
        flat = (1 - h0) ** n          # 每章投入都等於中位時的存活
        for c in range(1, n + 1):
            h = min(0.25, h0 * math.exp(s * (ref - E[c])))
            S *= 1 - h
            surv.append(S * (1 - h0) ** (n - c) / flat)   # 換算成相對平坦基線:>1 優於平坦,<1 劣於平坦
        runs.append({'prm': prm, 'E': E, 'S': surv})
    return runs


def mc_summary(runs, robust, w):
    n = len(runs[0]['E']) - 1
    low, high = [0] * (n + 1), [0] * (n + 1)
    for r in runs:
        e = r['E'][1:]
        lo, hi = pct(e, 0.10), pct(e, 0.90)
        for c in range(1, n + 1):
            if r['E'][c] <= lo:
                low[c] += 1
            if r['E'][c] >= hi:
                high[c] += 1
    d = len(runs)
    med = [0.0] + [statistics.median(r['E'][c] for r in runs) for c in range(1, n + 1)]
    stab = mean(spearman(r['E'][1:], med[1:]) for r in runs)
    send = [r['S'][n] for r in runs]
    return {'low': [x / d for x in low], 'high': [x / d for x in high], 'med': med, 'stab': stab,
            'rlow': [c for c in range(1, n + 1) if low[c] / d >= robust], 'rhigh': [c for c in range(1, n + 1) if high[c] / d >= robust],
            'send': send, 'vend': {v: [r['S'][b] for r in runs] for v, (a, b) in vol_ranges(w).items()}}


def param_sensitivity(runs):
    send = [r['S'][-1] for r in runs]
    return sorted(((spearman([r['prm'][k] for r in runs], send), k) for k in runs[0]['prm']), key=lambda x: -abs(x[0]))


def dominant_cause(series, P, c):
    mid = {k: (a + b) / 2 for k, (a, b) in P['sim'].items()}
    _, parts = simulate(series, mid)
    n = len(parts) - 1
    avg = {k: mean(parts[i][k] for i in range(1, n + 1)) for k in parts[1]}
    gap = {k: avg[k] - parts[c][k] for k in avg}
    return max(gap, key=gap.get)


# ---------- 彙總指標(供變異測試) ----------

def scalar_metrics(w, P, draws=60):
    series, oq, ap, lp, ls = sim_series(w, P)
    n = w['n']
    tr = thread_retention(w, P)
    cr, _ = character_returns(w, P)
    thr = P['ret']['低保留門檻']
    theta = P['loss']['高衝擊門檻 θ']
    aro = ap['aro'][1:]
    p25, p75 = pct(aro, 0.25), pct(aro, 0.75)
    runs = monte_carlo(series, P, draws=draws)
    ms = mc_summary(runs, P['mc']['穩健比例'], w)
    ev_val = [v for _, v, _ in ap['events']]
    a = dfa_alpha(ev_val)
    m = {
        'K1 戲劇反諷平均': mean(oq['DI']['任一'][1:]),
        'K1 謎團庫存平均': mean(oq['M'][1:]),
        'K2 開放問題平均': mean(oq['Q'][1:]),
        'K2 開放問題為零的章數': sum(1 for c in range(1, n + 1) if oq['Q'][c] == 0),
        'K3 伏筆回收時保留率平均': mean(r['R'] for r in tr),
        'K3 低保留伏筆數': sum(1 for r in tr if r['R'] < thr),
        'K3 角色重返保留率平均': mean(r['R'] for r in cr),
        'K4 轉換負荷平均': mean(lp['L'][1:]),
        'K4 轉換負荷p90': pct(lp['L'][1:], 0.9),
        'K5 喚起平均': mean(aro),
        'K5 低喚起最長連續章': longest_run([x <= p25 for x in aro])[0],
        'K5 高喚起最長連續章': longest_run([x >= p75 for x in aro])[0],
        'K5 效價DFA指數': a if a is not None else 0.0,
        'K6 損失衝擊總和': sum(ls['I'][1:]),
        'K6 無高衝擊損失最長連續章': longest_run([ls['I'][c] < theta for c in range(1, n + 1)])[0],
        'K7 書末相對存活指數': statistics.median(ms['send']),
        'K7 平均投入': mean(ms['med'][1:]),
    }
    return m


# ---------- 既有指標(僅供變異測試對照,數字須與正式工具一致) ----------

def legacy_metrics(w, P):
    G = gpos(w)
    n = w['n']
    tt = Q.tag_types()
    single_long, dists, bad = 0, [], 0
    for t in w['threads']:
        sets = [G[i] for i in t['setup'] + t['echo'] if i in G]
        recs = [G[i] for i in t['payoff'] if i in G]
        if not recs or not sets:
            continue
        d = min(recs) - max(sets)
        if d < 0:
            bad += 1
        dists.append(d)
        if d >= 40 and len(sets) == 1:
            single_long += 1
    stage = [e for e in w['events'] if e['kind'] == '演出']
    types = [Q.event_type(e['tags'], tt) for e in stage]
    best = 0
    for v in Q.VOLS:      # 與劇情量化.py 一致:每卷各自計算,取各卷最大
        run = 0
        for e in stage:
            if e['vol'] == v:
                run = 0 if any(tt.get(x) == '緩衝' for x in e['tags']) else run + 1
                best = max(best, run)
    lead_ch = set()
    for r in w['ledger']:
        if r['who'] in LEADS and r['rev'] == '不可逆' and r['id'] in G and G[r['id']] >= 1:
            lead_ch.add(G[r['id']])
    return {
        'C2 距離中位數': statistics.median(dists) if dists else 0.0,
        'C2 距離≥40卻單一設置點': single_long,
        'D1 最長連續無緩衝(事件)': best,
        'D1 緩衝事件占比': types.count('緩衝') / max(1, len(types)),
        'H3 回收早於設置': bad,
        'J1 男女主不可逆損失空窗(章)': L.runs_without(lead_ch, n)[0],
    }


# ---------- 格式檢查與自測 ----------

def problems(w=None):
    """資料與參數的格式檢查(供 檢查.py 呼叫):讀者知情的事件須存在且有章號、暗示不晚於確知;參數須涵蓋所有標籤。"""
    out = []
    w = w or load_world()
    P = load_params()
    G = gpos(w)
    staged = {e['id'] for e in w['events']}
    tags = set(Q.tag_types())
    for t in sorted(tags - set(P['tag'])):
        out.append(f'{PARAM_FILE}:標籤「{t}」沒有效價與喚起')
    for k in ('S0', 'β', '低保留門檻', '角色 S0'):
        if k not in P['ret']:
            out.append(f'{PARAM_FILE}:記憶保留缺少 {k}')
    for k in ('依附速率 k', '溫情加權', '未具名受害者依附度', '高衝擊門檻 θ', '生命', '亡故', '不可逆', '部分', '可逆'):
        if k not in P['loss']:
            out.append(f'{PARAM_FILE}:損失衝擊缺少 {k}')
    for k in ('抽樣次數', '種子', '穩健比例'):
        if k not in P['mc']:
            out.append(f'{PARAM_FILE}:蒙地卡羅設定缺少 {k}')
    for k, (lo, hi) in P['sim'].items():
        if lo > hi:
            out.append(f'{PARAM_FILE}:{k} 下限大於上限')
    seen = set()
    for s in w['secrets']:
        if s['id'] in seen:
            out.append(f'{READER_FILE}:{s["id"]} 重複')
        seen.add(s['id'])
        for k, lab in (('hint', '首見暗示'), ('known', '讀者確知'), ('lead_m', '男主得知'), ('lead_f', '女主得知')):
            if s[k] and s[k] not in staged:
                out.append(f'{READER_FILE}:{s["id"]} 的{lab} {s[k]} 不是有章號的事件')
        if s['hint'] in G and s['known'] in G and G[s['hint']] > G[s['known']]:
            out.append(f'{READER_FILE}:{s["id"]} 的暗示晚於讀者確知')
    return out


def selftest():
    """用已知答案的小資料檢查各函式;失敗回傳說明清單。"""
    bad = []

    def eq(name, got, want, tol=1e-6):
        if (isinstance(want, float) and abs(got - want) > tol) or (not isinstance(want, float) and got != want):
            bad.append(f'{name}:得 {got!r},應為 {want!r}')
    eq('longest_run', longest_run([0, 1, 1, 0, 1, 1, 1, 0]), (3, 5, 7))
    eq('spearman 反向', round(spearman([1, 2, 3, 4], [4, 3, 2, 1]), 6), -1.0)
    eq('ranks 同分', ranks([1, 1, 2]), [1.5, 1.5, 3.0])
    eq('months', months_of('初遇後 1 年 3 個月'), 15.0)
    eq('months 日', months_of('初遇後 30 日'), 1.0)
    eq('retention 無呼應', round(retention(50, [10], 40, 0.5), 6), round(math.exp(-1), 6))
    eq('retention 一次呼應', round(retention(50, [10, 30], 40, 0.5), 6), round(math.exp(-20 / 60), 6))
    rng = random.Random(1)
    noise = [rng.gauss(0, 1) for _ in range(400)]
    a = dfa_alpha(noise)
    if not (0.35 < a < 0.65):
        bad.append(f'DFA 白雜訊應接近 0.5,得 {a:.2f}')
    walk, x = [], 0.0
    for v in noise:
        x += v
        walk.append(x)
    b = dfa_alpha(walk)
    if not (b > 1.1):
        bad.append(f'DFA 隨機漫步應大於 1.1,得 {b:.2f}')
    xs = [i / 49 for i in range(50)]
    for name, f in SHAPES.items():
        top = shape_fit([f(x_) for x_ in xs])[0][1]
        if top != name:
            bad.append(f'形狀比對:{name} 被判成 {top}')
    P = load_params()
    # 單一事件的效價/喚起:悲劇(-0.9, 0.7)、日常(0.4, 0.1)
    v, a_ = event_va({'tags': ['悲劇', '日常']}, P)
    eq('event_va 效價', v, (-0.9 + 0.4) / 2)
    eq('event_va 喚起', a_, 0.6 * 0.7 + 0.4 * (0.7 + 0.1) / 2)
    # 微型世界:兩個事件、一條伏筆 → 開放問題只在設置到回收之間
    w = {'events': [{'id': 'T-1', 'vol': '第一部', 'ch': 1, 'g': 1, 'seq': 1, 'rel': '', 'months': 0.0, 'tags': ['日常'], 'kind': '演出', 'name': '', 'chars': ['男主'], 'scenes': ['甲']},
                    {'id': 'T-2', 'vol': '第一部', 'ch': 2, 'g': 2, 'seq': 2, 'rel': '', 'months': 0.0, 'tags': ['日常'], 'kind': '演出', 'name': '', 'chars': ['男主'], 'scenes': ['甲']},
                    {'id': 'T-3', 'vol': '第一部', 'ch': 4, 'g': 4, 'seq': 3, 'rel': '', 'months': 0.0, 'tags': ['日常'], 'kind': '演出', 'name': '', 'chars': ['男主'], 'scenes': ['甲']}],
         'bg': {}, 'n': 5, 'threads': [{'id': 'THR-T', 'title': '', 'setup': ['T-1'], 'echo': [], 'payoff': ['T-3'], 'secrets': []}],
         'secrets': [], 'ledger': [], 'titles': {}}
    oq = open_questions(w, P)
    eq('Q 區間', oq['Q'][1:], [1, 1, 1, 0, 0])
    tr = thread_retention(w, P)
    eq('伏筆保留率', round(tr[0]['R'], 6), round(math.exp(-3 / P['ret']['S0']), 6))
    # 損失:男主不可逆良心,依附度 1,基礎 0.8,可逆性 1
    w['ledger'] = [{'id': 'T-2', 'who': '男主', 'cat': '良心', 'loss': '', 'rev': '不可逆', 'src': ''}]
    ls = loss_profile(w, P)
    eq('損失衝擊', ls['I'][2], P['loss']['良心'] * P['loss']['不可逆'])
    # 轉換負荷:T-1→T-2 同場景、同主角、同時間 → 只有「新」項(第一事件的新角色/場景不計男主)
    lp = load_profile(w, P)
    eq('轉換負荷 章2', lp['L'][2], 0.0)
    return bad


# ---------- 報告 ----------

def vol_slices(w, arr):
    out = []
    for v, (a, b) in sorted(vol_ranges(w).items(), key=lambda kv: kv[1][0]):
        out.append((v, a, b, arr[a:b + 1]))
    return out


def report(w, P, draws=None):
    series, oq, ap, lp, ls = sim_series(w, P)
    n = w['n']
    out = []
    X = out.append
    X('# 體驗模擬報告\n')
    X('> 由 `python3 工具/體驗模擬.py` 產生,只讀。這是對「體驗的結構性前因」的推估,**不是品質分數,也沒有經過真人校準**。')
    X('> 參數都是假說([體驗參數](../設計規範/體驗參數.md))。只信方向與排序,不信絕對值;模擬器的結論只採用在多數參數組合下都成立者。\n')
    X(f'資料:{n} 章,{len([e for e in w["events"] if e["kind"] == "演出"])} 個演出事件,伏筆 {len(w["threads"])} 條,秘密 {len(w["secrets"])} 個,代價帳 {len(w["ledger"])} 筆。\n')

    # K1
    X('## K1 讀者知情(戲劇反諷與謎團庫存)\n')
    if not w['secrets']:
        X(f'沒有 {READER_FILE},略過。\n')
    else:
        X('戲劇反諷 = 讀者已確知、而男女主至少一人還不知道的秘密數;謎團 = 讀者看過暗示、但還沒確知的秘密數。來源:[讀者知情](../狀態/讀者知情.md)(草案)。\n')
        X('| 卷 | 戲劇反諷平均 | 最大 | 為零的章 | 謎團平均 | 最大 | 為零的章 |')
        X('|---|---|---|---|---|---|---|')
        for (v, a, b, di), (_, _, _, m) in zip(vol_slices(w, oq['DI']['任一']), vol_slices(w, oq['M'])):
            X(f'| {v} | {mean(di):.2f} | {max(di)} | {sum(1 for x in di if x == 0)} / {len(di)} | {mean(m):.2f} | {max(m)} | {sum(1 for x in m if x == 0)} / {len(m)} |')
        X('')
        for key, label_ in (('M', '謎團庫存'), ('DI', '戲劇反諷')):
            arr = oq['M'] if key == 'M' else oq['DI']['任一']
            X(f'{label_}逐章:')
            for v, a, b, sl in vol_slices(w, arr):
                X(f'- {v} `{spark(sl)}`')
            X('')
    # K2
    X('## K2 開放問題庫存\n')
    X('開放問題 = 已設置而未回收的伏筆,加上未被伏筆涵蓋、但讀者已見暗示而未確知的秘密。「保留加權」把讀者可能已經忘記的問題打折(用 K3 的保留模型)。\n')
    X('| 卷 | 平均 | 最少 | 最多 | 為零的章 | 保留加權平均 |')
    X('|---|---|---|---|---|---|')
    for (v, a, b, q), (_, _, _, qe) in zip(vol_slices(w, oq['Q']), vol_slices(w, oq['Qeff'])):
        X(f'| {v} | {mean(q):.1f} | {min(q)} | {max(q)} | {sum(1 for x in q if x == 0)} / {len(q)} | {mean(qe):.1f} |')
    X('')
    for v, a, b, sl in vol_slices(w, oq['Q']):
        X(f'- {v} 開放問題 `{spark(sl)}`')
    X('')
    # K3
    X('## K3 記憶保留\n')
    thr = P['ret']['低保留門檻']
    X(f"保留率 R = exp(−距離 / S),S = {P['ret']['S0']:g} × (1 + {P['ret']['β']:g} × 呼應次數)。R 是回收當章讀者仍記得這條伏筆的機率,低於 {thr:g} 者回收可能落空。\n")
    tr = sorted(thread_retention(w, P), key=lambda r: r['R'])
    X(f"- 伏筆 {len(tr)} 條,保留率平均 {mean(r['R'] for r in tr):.2f},低於 {thr:g} 的 {sum(1 for r in tr if r['R'] < thr)} 條。")
    X('- 敏感度:S0 取 20 / 40 / 80 時,低於門檻的條數 ' + ' / '.join(str(sum(1 for r in thread_retention(w, P, s) if r['R'] < thr)) for s in (20, 40, 80)) +
      '(排序不隨 S0 改變,因為 R 對 S0 單調;改變的是「多少條算低」,所以絕對條數不可信,只看哪些伏筆排在最前面)')
    X('\n保留率最低的 10 條:\n')
    X('| 伏筆 | 內容 | 回收章 | 最近接觸 | 空檔(章) | 接觸次數 | R |')
    X('|---|---|---|---|---|---|---|')
    for r in tr[:10]:
        X(f"| {r['id']} | {r['title'][:16]} | {chap_label(w, r['pay'])} | {chap_label(w, r['last']) if r['last'] else '—'} | {r['gap']} | {r['n']} | {r['R']:.2f} |")
    cr, napp = character_returns(w, P)
    low = sorted([r for r in cr if r['R'] < thr and napp[r['who']] >= 4], key=lambda r: r['R'])
    X(f"\n角色重返:出場 ≥4 章的角色,隔了很久才再出場、保留率低於 {thr:g} 的有 {len(low)} 次。最久的 8 次:\n")
    X('| 角色 | 上次 | 再現 | 空檔(章) | 此前出場章數 | R |')
    X('|---|---|---|---|---|---|')
    for r in sorted(low, key=lambda r: -r['gap'])[:8]:
        X(f"| {r['who']} | {chap_label(w, r['from'])} | {chap_label(w, r['to'])} | {r['gap']} | {r['n']} | {r['R']:.2f} |")
    X('')
    # K4
    X('## K4 事件索引轉換負荷\n')
    X(f"逐章累計:時間跳躍或倒退、場景轉換、主角組合改變、配角更替,加上新角色、新場景、新伏筆的首次出現。意圖與因果沒有資料欄,未計(見 [體驗參數](../設計規範/體驗參數.md))。{lp['unparsed']} / {lp['stage']} 個演出事件的時間無法換算,不計時間轉換。\n")
    X('| 卷 | 平均 | p90 | 最大(章) |')
    X('|---|---|---|---|')
    for v, a, b, sl in vol_slices(w, lp['L']):
        mx = max(sl)
        X(f'| {v} | {mean(sl):.2f} | {pct(sl, 0.9):.2f} | {mx:.2f}(第 {a + sl.index(mx) - Q.OFF[v]} 章) |')
    X('\n負荷最高的 8 章:\n')
    X('| 章 | 負荷 | 時間 | 空間 | 主角 | 配角 | 新增 |')
    X('|---|---|---|---|---|---|---|')
    for c in sorted(range(1, n + 1), key=lambda c: -lp['L'][c])[:8]:
        k = lp['comp'][c]
        X(f"| {chap_label(w, c)} {chap_title(w, c)} | {lp['L'][c]:.1f} | {k['time']:.1f} | {k['space']:.1f} | {k['lead']:.1f} | {k['cast']:.1f} | {k['new']:.1f} |")
    X('')
    for v, a, b, sl in vol_slices(w, lp['L']):
        X(f'- {v} 轉換負荷 `{spark(sl)}`')
    X('')
    # K5
    X('## K5 效價與喚起軌跡(依標籤,規劃意圖)\n')
    X('效價與喚起由標籤對照表換算([體驗參數](../設計規範/體驗參數.md)),所以反映的是**作者意圖的節奏**,不是正文實際寫出的情緒。形狀比對只是描述:Reagan 等(2016)的六型是對大量小說的歸納,Boyd 等(2020)發現遵循常見結構與受歡迎程度無關。\n')
    X('| 卷 | 最貼近的形狀(r) | 次貼近 | 喚起峰值章(位置) | 末三章喚起 / 全卷 | 末三章效價 |')
    X('|---|---|---|---|---|---|')
    pe = {}
    for (v, a, b, val), (_, _, _, aro) in zip(vol_slices(w, ap['val']), vol_slices(w, ap['aro'])):
        fit = shape_fit(val)
        pk = aro.index(max(aro))
        pe[v] = (max(aro), mean(aro[-3:]))
        X(f"| {v} | {fit[0][1]}({fit[0][0]:.2f}) | {fit[1][1]}({fit[1][0]:.2f}) | 第 {pk + 1} 章({pk / max(1, len(aro) - 1):.0%}) | {mean(aro[-3:]) / mean(aro):.2f} | {mean(val[-3:]):+.2f} |")
    allaro = ap['aro'][1:]
    p25, p75 = pct(allaro, 0.25), pct(allaro, 0.75)
    lo = longest_run([x <= p25 for x in allaro])
    hi = longest_run([x >= p75 for x in allaro])
    X(f"\n- 低喚起(≤ 全書 25 分位 {p25:.2f})最長連續 {lo[0]} 章({chap_label(w, lo[1])} 至 {chap_label(w, lo[2])});高喚起(≥ 75 分位 {p75:.2f})最長連續 {hi[0]} 章({chap_label(w, hi[1])} 至 {chap_label(w, hi[2])})。")
    ac = pearson(allaro[:-1], allaro[1:])
    X(f'- 喚起的一階自相關 {ac:.2f}(接近 0 為隨機起伏,偏高為成段的長高潮或長平淡)。')
    a, mu, z = dfa_with_null([v for _, v, _ in ap['events']], seed=int(P['mc']['種子']))
    if a is not None:
        X(f'- 效價序列(逐事件)的 DFA 標度指數 α = {a:.2f};把事件順序打亂 200 次的對照約 {mu:.2f}(z = {z:+.1f})。Bizzoni 等在安徒生童話上看到 0.55 至 0.65 的作品評價較好,但那是相關性、且評價是代理,**只當描述**。')
    X('\n逐章喚起(▁低 ⇢ █高)與效價:\n')
    for (v, a2, b2, sl), (_, _, _, vs) in zip(vol_slices(w, ap['aro']), vol_slices(w, ap['val'])):
        X(f'- {v} 喚起 `{spark(sl)}`')
        X(f'- {v} 效價 `{spark(vs)}`')
    X('')
    # K6
    X('## K6 損失的情感衝擊\n')
    th = P['loss']['高衝擊門檻 θ']
    X(f"衝擊 = 類別基礎值 × 依附度 × 可逆性係數。承擔者是男女主時依附度為 1;「亡故」看逝者:讀者對他/她的依附度 = 1 − exp(−k × 此前的加權同場數)。無具名逝者用暫定值 {P['loss']['未具名受害者依附度']:g}。\n")
    X('| θ(有損失的章,衝擊 ≥ θ) | ' + ' | '.join(f'{t:g}' for t in (0.3, 0.5, 0.8)) + ' |')
    X('|---|---|---|---|')
    X('| 最長連續沒有損失的章數 | ' + ' | '.join(str(longest_run([ls['I'][c] < t for c in range(1, n + 1)])[0]) for t in (0.3, 0.5, 0.8)) + ' |')
    r0 = longest_run([ls['I'][c] < th for c in range(1, n + 1)])
    X(f'\n- θ={th:g} 時,最長空窗 {r0[0]} 章({chap_label(w, r0[1])} 至 {chap_label(w, r0[2])})。對照 J1(男女主不可逆損失)的空窗只看筆數,這裡看分量。')
    X('\n衝擊最高的 10 筆:\n')
    X('| 事件 | 章 | 承擔者 | 類別 | 逝者 | 依附度 | 衝擊 |')
    X('|---|---|---|---|---|---|---|')
    for it in sorted(ls['items'], key=lambda x: -x['impact'])[:10]:
        X(f"| {it['id']} | {chap_label(w, it['g'])} | {it['who']} | {it['cat']}/{it['rev']} | {it['lost']} | {it['att']:.2f} | {it['impact']:.2f} |")
    weak = [it for it in ls['items'] if it['impact'] < 0.15]
    X(f'\n衝擊 < 0.15 的帳目有 {len(weak)} 筆(讀者可能無感):' + '、'.join(f"{it['id']}({it['cat']}/{it['rev']}{',逝者 ' + it['lost'] if it['lost'] else ''},{it['impact']:.2f})" for it in weak[:12]) + ('…' if len(weak) > 12 else ''))
    X('')
    X('死亡類帳目的逝者與讀者依附度:\n')
    X('| 事件 | 逝者 | 依附度 |')
    X('|---|---|---|')
    for it in sorted([x for x in ls['items'] if x['cat'] == '亡故'], key=lambda x: x['g']):
        X(f"| {it['id']} {chap_label(w, it['g'])} | {it['lost']} | {it['att']:.2f} |")
    X('')
    for v, a2, b2, sl in vol_slices(w, ls['I']):
        X(f'- {v} 損失衝擊 `{spark(sl)}`')
    X('')
    # K7
    X('## K7 讀者模擬器(蒙地卡羅)\n')
    runs = monte_carlo(series, P, draws=draws)
    robust = P['mc']['穩健比例']
    ms = mc_summary(runs, robust, w)
    X(f"逐章狀態:好奇(保留加權的開放問題)、喚起(絕對強度加上高出適應水準的對比)、損失衝擊、轉換負荷超載、疲勞(持續高喚起累積)、無聊(持續低喚起累積)合成「投入」E;E 低於「普通章」時放棄機率上升。{len(runs)} 組參數抽自 [體驗參數](../設計規範/體驗參數.md) 的範圍(固定種子)。\n")
    X(f"- 排序穩定度:各組參數下的逐章投入排序,與中位排序的平均斯皮爾曼相關 = **{ms['stab']:.2f}**(越接近 1,結論越不依賴參數)。")
    X(f"- 「相對存活指數」不是留存率,是相對於「每章都是普通章」的比值:書末中位 {statistics.median(ms['send']):.2f}(1 = 與「每章都是普通章」的書同樣留得住)(10% 至 90% 區間 {pct(ms['send'], .1):.2f} 至 {pct(ms['send'], .9):.2f})。各卷結束:" +
      ';'.join(f"{v} {statistics.median(s):.2f}" for v, s in ms['vend'].items()))
    X('\n對書末存活指數影響最大的參數(斯皮爾曼相關):' + '、'.join(f'{k} {r:+.2f}' for r, k in param_sensitivity(runs)[:4]))
    X(f"\n**穩健的低谷**(≥{robust:.0%} 的參數組合下,該章投入落在全書最低 10%):{len(ms['rlow'])} 章\n")
    if ms['rlow']:
        X('| 章 | 出現比例 | 主要缺什麼 |')
        X('|---|---|---|')
        for c in ms['rlow']:
            X(f"| {chap_label(w, c)} | {ms['low'][c]:.0%} | {dominant_cause(series, P, c)} |")
    X(f"\n**穩健的高峰**(最高 10%):{len(ms['rhigh'])} 章:" + ('、'.join(chap_label(w, c) for c in ms['rhigh']) or '無'))
    soft = [c for c in range(1, n + 1) if 0.5 <= ms['low'][c] < robust]
    X(f"\n半穩健的低谷(50% 至 {robust:.0%}):{len(soft)} 章:" + ('、'.join(chap_label(w, c) for c in soft) or '無'))
    X('\n逐章中位投入:\n')
    for v, a, b, sl in vol_slices(w, ms['med']):
        X(f'- {v} `{spark(sl)}`')
    X('\n## 讀法與限制\n')
    X('- 這些量是作者規劃資料的函數:標籤、伏筆登記、代價帳都是作者填的,寫得越齊全指標越完整,填得不一致就會失真。')
    X('- 低谷與高峰只是「這個模型在多數參數下都這樣看」,不等於真人會無聊或興奮;要驗證,看 `python3 工具/變異測試.py` 的鑑別力報告與日後的真人校準。')
    X('- 不要把任何一項當目標去最佳化(Goodhart)。有疑慮的章段,用 [讀者測試](../設計規範/讀者測試.md) 交給全新 session 看,再決定要不要改劇情,重大改動先走[選項對照](../設計規範/選項對照.md)。')
    return '\n'.join(out) + '\n', {'series': series, 'oq': oq, 'ap': ap, 'lp': lp, 'ls': ls, 'ms': ms}


def write_csv(path, w, R_):
    ms = R_['ms']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('章序,卷章,開放問題,保留加權,謎團,戲劇反諷,轉換負荷,效價,喚起,損失衝擊,中位投入,低谷比例\n')
        for c in range(1, w['n'] + 1):
            f.write(','.join(str(x) for x in (
                c, chap_label(w, c), R_['oq']['Q'][c], f"{R_['oq']['Qeff'][c]:.3f}", R_['oq']['M'][c], R_['oq']['DI']['任一'][c],
                f"{R_['lp']['L'][c]:.3f}", f"{R_['ap']['val'][c]:.3f}", f"{R_['ap']['aro'][c]:.3f}", f"{R_['ls']['I'][c]:.3f}",
                f"{ms['med'][c]:.3f}", f"{ms['low'][c]:.2f}")) + '\n')


def main(argv):
    if '--自測' in argv:
        bad = selftest()
        print('自測:' + ('全部通過' if not bad else f'{len(bad)} 項失敗'))
        for b in bad:
            print('  ✗', b)
        return 1 if bad else 0
    P = load_params()
    w = load_world()
    draws = int(argv[argv.index('--draws') + 1]) if '--draws' in argv else None
    text, R_ = report(w, P, draws)
    if '--csv' in argv:
        write_csv(argv[argv.index('--csv') + 1], w, R_)
    if '--out' in argv:
        with open(argv[argv.index('--out') + 1], 'w', encoding='utf-8') as f:
            f.write(text)
        print('已寫入', argv[argv.index('--out') + 1])
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
