#!/usr/bin/env python3
"""變異測試:檢驗劇情量測有沒有鑑別力。只讀,不改任何檔案(擾動都在記憶體裡)。

沒有真人資料就沒有地面真值,但我們知道哪些改動「一定讓劇情變差」(刪掉伏筆呼應、打亂章序、抹掉所有代價……)。
一個指標若對這些破壞毫無反應,就沒有資格當診斷;方向相反,表示定義有問題。注意這檢查的是「接線」(指標有沒有接上資料、方向對不對),不是「效度」(是否等於讀者感受)。這是軟體工程的突變測試與蛻變測試(metamorphic testing)搬到劇情上。

用法:
  python3 工具/變異測試.py                # 完整報告
  python3 工具/變異測試.py --out 檔案.md   # 寫成檔案
  python3 工具/變異測試.py --strict       # 基線與正式工具不一致、或有指標方向錯誤時結束碼為 1
  python3 工具/變異測試.py --draws 40     # 蒙地卡羅抽樣次數(預設 40;變異測試只比較差異,不需要多)

判讀:
  ✓ 朝預期方向變動且超過門檻   ✗ 朝相反方向   ○ 沒有明顯變動(預期有反應卻不動 = 鈍)   · / ↑ / ↓ 沒有預期方向時的觀察
門檻:相對變化 ≥ 2%;蒙地卡羅衍生的指標另需大於抽樣雜訊(換 5 個種子的標準差)的 3 倍。
"""
import copy, os, random, re, statistics, subprocess, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 劇情量化 as Q
import 體驗模擬 as X

UP, DOWN = '↑', '↓'



# ---------- 擾動 ----------

def p_no_echo(w, rng):
    for t in w['threads']:
        t['echo'] = []


def p_early_payoff(w, rng):
    G = X.gpos(w)
    by_g = {}
    for e in w['events']:
        by_g.setdefault(e['g'], e['id'])
    for t in w['threads']:
        tc = X.touches_of(t, G)
        if tc:
            target = min(w['n'], max(1, tc[0]) + 2)
            while target not in by_g and target < w['n']:
                target += 1
            t['payoff'] = [by_g.get(target, t['payoff'][0] if t['payoff'] else None)]
            t['echo'] = []


def p_insert_buffer(w, rng, count=10):
    pivot_vol = '第二部'
    pivot = Q.OFF[pivot_vol] + 24
    for e in w['events']:
        if e['g'] > pivot:
            e['g'] += count
    base = next(e for e in w['events'] if e['g'] == pivot)
    for k in range(1, count + 1):
        for j in range(2):
            w['events'].append({'id': f'ZZ-{k:03d}{j}', 'vol': pivot_vol, 'ch': 0, 'g': pivot + k, 'seq': 10 ** 6 + k * 10 + j,
                                'rel': base['rel'], 'months': base['months'], 'tags': ['日常', '敘事'], 'kind': '演出',
                                'name': '填充', 'chars': ['男主'], 'scenes': ['填充場景']})
    w['n'] += count
    w['events'].sort(key=lambda r: (r['g'], Q.VOLS.index(r['vol']), r['seq']))


def p_shuffle_chapters(w, rng):
    for v in Q.VOLS:
        chs = sorted({e['ch'] for e in w['events'] if e['vol'] == v})
        perm = chs[:]
        rng.shuffle(perm)
        mp = dict(zip(chs, perm))
        for e in w['events']:
            if e['vol'] == v:
                e['ch'] = mp[e['ch']]
                e['g'] = Q.gidx(v, e['ch'])
    w['events'].sort(key=lambda r: (r['g'], Q.VOLS.index(r['vol']), r['seq']))


def p_no_ledger(w, rng):
    w['ledger'] = []


def p_all_reversible(w, rng):
    for r in w['ledger']:
        r['rev'] = '可逆'


def p_reveal_up_front(w, rng):
    first = w['events'][0]['id']
    for s in w['secrets']:
        s['hint'] = s['known'] = first


def p_no_hints(w, rng):
    for s in w['secrets']:
        s['hint'] = None


def p_flatten_heavy(w, rng):
    heavy = {'悲劇', '死亡', '戰爭', '驚魂', '揭露'}
    for e in w['events']:
        e['tags'] = ['日常' if t in heavy else t for t in e['tags']]


def p_new_cast(w, rng):
    for k, e in enumerate(w['events']):
        e['chars'] = [c for c in e['chars'] if c in Q.LEADS] + [f'新人{k}']


def p_shuffle_time(w, rng):
    ms = [e['months'] for e in w['events'] if e['months'] is not None]
    rng.shuffle(ms)
    it = iter(ms)
    for e in w['events']:
        if e['months'] is not None:
            e['months'] = next(it)


def p_drop_half_threads(w, rng):
    w['threads'] = [t for i, t in enumerate(w['threads']) if i % 2 == 0]


def p_thin_cast(w, rng):
    """出場 ≥3 章的配角,只保留第一次與最後一次出場,中間全拿掉(拉長重返間隔)。"""
    chaps = {}
    for e in w['events']:
        for c in e['chars']:
            if c not in Q.LEADS:
                chaps.setdefault(c, set()).add(e['g'])
    for c, gs in chaps.items():
        if len(gs) >= 3:
            keep = {min(gs), max(gs)}
            for e in w['events']:
                if c in e['chars'] and e['g'] not in keep:
                    e['chars'].remove(c)


def p_shuffle_tags(w, rng):
    tags = [list(e['tags']) for e in w['events']]
    rng.shuffle(tags)
    for e, t in zip(w['events'], tags):
        e['tags'] = t


def p_all_conflict(w, rng):
    for e in w['events']:
        e['tags'] = ['衝突' if t in ('日常', '溫情', '幽默', '敘事', '成長', '設定', '傳說', '相遇') else t for t in e['tags']]


PERTURBATIONS = [
    # (編號, 名稱, 函式, 預期:{指標: ↑/↓})
    ('M01', '刪掉所有伏筆的中途呼應', p_no_echo,
     {'K3 伏筆回收時保留率平均': DOWN, 'K3 低保留伏筆數': UP, 'C2 距離≥40卻單一設置點': UP, 'K7 平均投入': DOWN}),
    ('M02', '所有伏筆在設置後 2 章就回收', p_early_payoff,
     {'K2 開放問題平均': DOWN, 'K2 開放問題為零的章數': UP, 'C2 距離中位數': DOWN, 'K7 平均投入': DOWN}),
    ('M03', '在第二部中段插入 10 章純日常緩衝', p_insert_buffer,
     {'K5 低喚起最長連續章': UP, 'K7 平均投入': DOWN, 'K7 書末相對存活指數': DOWN, 'J1 男女主不可逆損失空窗(章)': UP,
      'K6 無高衝擊損失最長連續章': UP, 'D1 緩衝事件占比': UP}),
    ('M04', '打亂各卷章序', p_shuffle_chapters,
     {'K4 轉換負荷平均': UP, 'K4 轉換負荷p90': UP, 'H3 回收早於設置': UP}),
    ('M05', '刪光代價帳', p_no_ledger,
     {'K6 損失衝擊總和': DOWN, 'K6 無高衝擊損失最長連續章': UP, 'J1 男女主不可逆損失空窗(章)': UP, 'K7 平均投入': DOWN}),
    ('M06', '代價帳全部改成「可逆」', p_all_reversible,
     {'K6 損失衝擊總和': DOWN, 'J1 男女主不可逆損失空窗(章)': UP, 'K6 無高衝擊損失最長連續章': UP}),
    ('M07', '所有秘密一開場就讓讀者確知', p_reveal_up_front,
     {'K1 謎團庫存平均': DOWN, 'K1 戲劇反諷平均': UP}),
    ('M08', '刪光所有秘密的暗示', p_no_hints,
     {'K1 謎團庫存平均': DOWN}),
    ('M09', '把悲劇、死亡、戰爭、驚魂、揭露全改成日常', p_flatten_heavy,
     {'K5 喚起平均': DOWN, 'K5 高喚起最長連續章': DOWN, 'D1 緩衝事件占比': UP, 'D1 最長連續無緩衝(事件)': DOWN, 'K7 平均投入': DOWN}),
    ('M10', '每個事件都換全新配角', p_new_cast,
     {'K4 轉換負荷平均': UP, 'K7 平均投入': DOWN}),
    ('M11', '打散所有事件的相對時間', p_shuffle_time,
     {'K4 轉換負荷平均': UP, 'K4 轉換負荷p90': UP}),
    ('M12', '隨機刪掉一半伏筆', p_drop_half_threads,
     {'K2 開放問題平均': DOWN, 'K7 平均投入': DOWN}),
    ('M13', '配角只留第一次與最後一次出場', p_thin_cast,
     {'K3 角色重返保留率平均': DOWN}),
    ('M14', '事件標籤隨機換位(破壞前後連貫)', p_shuffle_tags,
     {'K5 效價DFA指數': DOWN}),
    ('M15', '所有緩衝類標籤改成「衝突」(全書不喘息)', p_all_conflict,
     {'D1 最長連續無緩衝(事件)': UP, 'D1 緩衝事件占比': DOWN, 'K5 低喚起最長連續章': DOWN, 'K7 平均投入': DOWN}),
]

# 預期不動的對照(負對照):擾動與該指標無關,若指標動了表示它讀了不該讀的東西
NEGATIVE = [
    ('M05', 'K2 開放問題平均'), ('M05', 'K4 轉換負荷平均'), ('M05', 'K5 喚起平均'),
    ('M07', 'K6 損失衝擊總和'), ('M07', 'K4 轉換負荷平均'),
    ('M09', 'K2 開放問題平均'), ('M09', 'K3 伏筆回收時保留率平均'),
    ('M11', 'K5 喚起平均'), ('M11', 'K2 開放問題平均'),
]


# ---------- 量測與比較 ----------

SEEDS = 5


def all_metrics(w, P, draws, seed_shift=0):
    p = dict(P)
    p['mc'] = dict(P['mc'], 種子=P['mc']['種子'] + seed_shift)
    m = X.scalar_metrics(w, p, draws=draws)
    m.update(X.legacy_metrics(w, P))
    return m


def runs_of(w, P, draws):
    return [all_metrics(w, P, draws, k) for k in range(SEEDS)]


def paired(base_runs, new_runs, key):
    """基線與擾動後用相同的 5 個種子(同一批參數抽樣)配對比較。回傳 (基線均值, 擾動後均值, 判定)。
    判定:平均差的相對變化 ≥ 2%,且至少 4/5 個種子同向,才算有變動。"""
    b = [r[key] for r in base_runs]
    n = [r[key] for r in new_runs]
    mb, mn = mean(b), mean(n)
    diffs = [y - x for x, y in zip(b, n)]
    rel = abs(mn - mb) / max(abs(mb), 1e-9)
    pos, neg = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    if mn == mb or rel < 0.02:
        return mb, mn, 0
    if pos >= 4:
        return mb, mn, 1
    if neg >= 4:
        return mb, mn, -1
    return mb, mn, 0


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def classify(exp, ch):
    if exp is None:
        return '·' if ch == 0 else UP if ch > 0 else DOWN
    want = 1 if exp == UP else -1
    return '○' if ch == 0 else '✓' if ch == want else '✗'


# ---------- 基線核對:重算的既有指標須與正式工具一致 ----------

def verify_baseline(w, P):
    probs = []
    mine = X.legacy_metrics(w, P)

    def run(args):
        return subprocess.run([sys.executable, '-I'] + args, capture_output=True, text=True, cwd=os.getcwd()).stdout
    out = run(['工具/劇情量化.py'])
    m = re.search(r'卻只有單一設置點[^:]*:(\d+) 條', out)
    if m and int(m.group(1)) != mine['C2 距離≥40卻單一設置點']:
        probs.append(f"C2 單一設置點:正式工具 {m.group(1)},重算 {mine['C2 距離≥40卻單一設置點']}")
    runs = [int(x) for x in re.findall(r'\| (?:序卷|第一部|第二部|第三部) \| \d+% \| \d+% \| \d+% \| (\d+) / \d+ \|', out)]
    if runs and max(runs) != mine['D1 最長連續無緩衝(事件)']:
        probs.append(f"D1 最長連續無緩衝:正式工具 {max(runs)},重算 {mine['D1 最長連續無緩衝(事件)']}")
    out2 = subprocess.run([sys.executable, '-I', '工具/代價帳.py'], capture_output=True, text=True).stdout
    m = re.search(r'男女主任一,不可逆:最長 (\d+) 章', out2)
    if m and int(m.group(1)) != mine['J1 男女主不可逆損失空窗(章)']:
        probs.append(f"J1:正式工具 {m.group(1)},重算 {mine['J1 男女主不可逆損失空窗(章)']}")
    if not (m and runs):
        probs.append('無法從正式工具輸出解析對照值(輸出格式變了?)')
    return probs


def main(argv):
    P = X.load_params()
    draws = int(argv[argv.index('--draws') + 1]) if '--draws' in argv else 40
    w0 = X.load_world()
    out = []
    A = out.append
    A('# 變異測試報告\n')
    A('> 由 `python3 工具/變異測試.py` 產生,只讀。目的:檢驗指標有沒有鑑別力。方法與判讀見該檔開頭與 [體驗量化研究](../設計規範/體驗量化研究.md) X12。\n')
    probs = verify_baseline(w0, P)
    A('## 基線核對\n')
    A('重算的既有指標(C2、D1、J1)須與正式工具輸出一致,否則擾動前後的比較沒有意義。\n')
    A('- ' + ('✓ 一致' if not probs else '✗ ' + ';'.join(probs)))
    base_runs = runs_of(w0, P, draws)
    base = {k: mean(r[k] for r in base_runs) for k in base_runs[0]}
    sd = {k: statistics.pstdev([r[k] for r in base_runs]) for k in base}
    A('\n## 基線與抽樣雜訊\n')
    A(f'蒙地卡羅衍生的指標(K7)用 {SEEDS} 個種子重跑;擾動後用**同樣的種子**配對比較,所以雜訊不會被誤當成變動。至少 4/5 個種子同向且平均相對變化 ≥ 2%,才算「有變動」。\n')
    A('| 指標 | 基線 | 換種子的標準差 |')
    A('|---|---|---|')
    for k, v in base.items():
        A(f'| {k} | {v:.3g} | {sd[k]:.3g} |')
    has_sec = bool(w0['secrets'])
    results = {}
    for pid, name, fn, exp in PERTURBATIONS:
        if pid in ('M07', 'M08') and not has_sec:
            continue
        w = copy.deepcopy(w0)
        fn(w, random.Random(int(P['mc']['種子']) + int(pid[1:])))
        nr = runs_of(w, P, draws)
        results[pid] = {k: paired(base_runs, nr, k) for k in base}
    A('\n## 擾動 × 指標\n')
    A('只列有預期方向的格子與負對照;完整觀察在下一節。\n')
    A('| 擾動 | 指標 | 預期 | 基線 → 擾動後 | 結果 |')
    A('|---|---|---|---|---|')
    hit, miss, wrong = {}, {}, {}
    for pid, name, fn, exp in PERTURBATIONS:
        if pid not in results:
            continue
        for k, e in exp.items():
            b, n_, ch = results[pid][k]
            c = classify(e, ch)
            A(f'| {pid} {name} | {k} | {e} | {b:.3g} → {n_:.3g} | {c} |')
            (hit if c == '✓' else wrong if c == '✗' else miss).setdefault(k, []).append(pid)
    A('\n負對照(與擾動無關的指標,預期不動):\n')
    A('| 擾動 | 指標 | 基線 → 擾動後 | 結果 |')
    A('|---|---|---|---|')
    neg_bad = []
    for pid, k in NEGATIVE:
        if pid not in results:
            continue
        b, n_, ch = results[pid][k]
        ok = '✓ 沒動' if ch == 0 else '✗ 動了'
        if ch != 0:
            neg_bad.append((pid, k))
        A(f'| {pid} | {k} | {b:.3g} → {n_:.3g} | {ok} |')
    A('\n## 完整觀察(每個擾動對每個指標的變動方向)\n')
    keys = list(base)
    A('| 擾動 | ' + ' | '.join(k.split(' ', 1)[0] + ' ' + k.split(' ', 1)[1][:6] for k in keys) + ' |')
    A('|---|' + '---|' * len(keys))
    for pid, name, fn, exp in PERTURBATIONS:
        if pid not in results:
            continue
        A(f'| {pid} | ' + ' | '.join(classify(exp.get(k), results[pid][k][2]) for k in keys) + ' |')
    A('\n欄位依序:' + '、'.join(keys))
    A('\n## 結論:各指標有沒有反應\n')
    A('| 指標 | 預期反應正確 | 預期反應卻不動(鈍) | 方向相反 | 判定 |')
    A('|---|---|---|---|---|')
    verdict_bad = []
    for k in keys:
        h, m_, wr = hit.get(k, []), miss.get(k, []), wrong.get(k, [])
        if not (h or m_ or wr):
            v = '沒有任何擾動預期它動(未檢驗)'
        elif wr:
            v = '**方向相反,檢視定義**'
            verdict_bad.append(k)
        elif not h:
            v = '**全部不動,指標沒接上(或擾動太小)**'
            verdict_bad.append(k)
        elif m_:
            v = f'部分鈍({len(h)}/{len(h) + len(m_)})'
        else:
            v = '有反應'
        A(f"| {k} | {'、'.join(h) or '—'} | {'、'.join(m_) or '—'} | {'、'.join(wr) or '—'} | {v} |")
    A('\n說明:')
    A('- 「未檢驗」不等於有用:要新增一條會讓該指標變動的擾動,才能判斷。')
    A('- 鈍的原因可能是指標真的不敏感,也可能是擾動太小、或另一個機制抵銷。看「基線 → 擾動後」那一欄,判斷是哪一種。')
    A('- **這個測試檢查的是接線,不是效度。** 例如「刪掉呼應 → 保留率下降」幾乎是定義使然;它能抓到的是指標沒接上資料、方向寫反、被不相干的東西影響。指標是否真的對應讀者感受,只有真人校準(X14)能回答。')
    A('- M09、M15 在調整讀者模擬器時被當成「模型必須通過的常識關卡」(刪光高潮不應讓投入變好、全書不喘息不應更好),所以它們對 K7 已不是獨立檢驗;其餘擾動沒有用來調模型。M15 對 K7 仍然鈍:模型還無法表現「一路高強度」造成的倦怠,這是已知弱點。')
    if not has_sec:
        A(f'- 因為沒有 {X.READER_FILE},M07、M08 與 K1 相關檢驗略過。')
    text = '\n'.join(out) + '\n'
    if '--out' in argv:
        with open(argv[argv.index('--out') + 1], 'w', encoding='utf-8') as f:
            f.write(text)
        print('已寫入', argv[argv.index('--out') + 1])
    else:
        sys.stdout.write(text)
    if '--strict' in argv and (probs or wrong or neg_bad):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
