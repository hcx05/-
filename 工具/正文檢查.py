#!/usr/bin/env python3
"""正文檢查:對小說正文做事實與格式層的機器檢查。不評文學品質。

用法:
    python3 工具/正文檢查.py 正文/第一部/第1章_劍門秋雨.md [更多檔]
    python3 工具/正文檢查.py --全部                 # 檢查 正文/ 下所有章
    python3 工具/正文檢查.py 檔 --場景卡 正文/計畫/第一部/第02章.場景卡.md
結束碼:有「錯誤」為 1,只有「提示」為 0。

錯誤(必須修):格式、規劃用語外洩、術語避免寫法、現代用詞、稱謂禁用、揭露節點(硬)、場景卡禁揭詞、
              帳本缺失或格式不符、大綱要點未對照、帳本回補路徑不存在。
提示(需人判斷):已故者出現、未在大綱出現的已登記人名、疑似未登記的新人名、揭露節點(提示級)、
                待決稱呼、字數落差、套語與短段的密度。
提示與寫作規範第九節一致:自動偵測只是提示,不是文學上的通過或失敗。
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L

MODERN = ['公里', '公尺', '公分', '公斤', '分鐘', '秒鐘', '小時(?!候)', '星期', '禮拜', '手機', '電話', '電燈',
          '電影', '汽車', '火車', '飛機', '塑膠', '橡膠', '水泥', '咖啡', '香菸', '警察', '百分之', '公元', '西元']
PLAN_PATTERNS = [
    (r'(?:PRO|P[123])-\d{3}', '事件編號'),
    (r'(?:FACT|DEC|THR|SEC|TXT|ITM)-', '規劃編號'),
    (r'\bL\d{1,2}\b', '戰力等級數字'),
    (r'戰力等級', '戰力等級用語'),
    (r'男主', '規劃用語「男主」'),
    (r'女主(?!人)', '規劃用語「女主」'),
]
PRONOUN_STOP = set('他她它我你您咱們他們她們大家有人那人此人這人眾人旁人別人什麼誰'.split()) | {
    '少年', '少女', '老人', '老漢', '婦人', '男人', '女人', '孩子', '那少年', '那少女', '一個', '那人', '對方', '眾人',
    '兩人', '三人', '那老漢', '那婦人', '那孩子', '黑衣人', '紅衣人'}


def known_names(o):
    names = set(L.parse_id_map()['角色']) - {'男主', '女主'}
    for al in L.NAME_ALIASES.values():
        names |= set(al)
    names |= {k for k in L.NAME_ALIASES}
    return names


def lines_of(text):
    return text.split('\n')


def check_file(path, require_ledger=True, scene_card=None):
    """回傳 (errors, warns);各為 [(代碼, 行號, 訊息)]。"""
    errs, warns = [], []
    text = L.read(path)
    lines = lines_of(text)
    base = os.path.basename(path)
    m = re.match(r'第(\d+)章_(.+)\.md', base)
    parts = os.path.normpath(path).split(os.sep)
    vol = parts[-2]
    if not m or vol not in L.VOLS:
        errs.append(('E01', 1, '檔案應位於 正文/{卷}/第N章_標題.md'))
        return errs, warns
    n, title = int(m.group(1)), m.group(2)
    o = L.get_outline(vol, n)

    # E01 標題、E02 引言
    h = re.match(r'# 第 (\d+) 章 · (.+)', lines[0])
    if not h or int(h.group(1)) != n or h.group(2).strip() != title:
        errs.append(('E01', 1, f'首行應為「# 第 {n} 章 · {title}」'))
    if len(lines) < 3 or not lines[2].startswith('> 視角:') or '對應事件:' not in lines[2]:
        errs.append(('E02', 3, '第 3 行應為「> 視角:… ｜ 時間:… ｜ 對應事件:…」'))
    elif o:
        ids = sorted(re.findall(r'[A-Z0-9]+-\d+', lines[2].split('對應事件:')[-1]))
        if ids != sorted(o['events']):
            errs.append(('E02', 3, f'對應事件 {ids} 與章節大綱 {sorted(o["events"])} 不一致'))

    # E13 引言行的男主歲數須落在本章事件對應的時間線區間
    if o and len(lines) > 2:
        mm = re.search(r'(\d+)\s*歲', lines[2])
        if mm:
            ages = L.timeline_ages(vol)
            lo = hi = None
            for e in o['events']:
                if e in ages and ages[e][0]:
                    lo = ages[e][0][0] if lo is None else min(lo, ages[e][0][0])
                    hi = ages[e][0][1] if hi is None else max(hi, ages[e][0][1])
            if lo is not None and not (lo <= int(mm.group(1)) <= hi):
                errs.append(('E13', 3, f'引言行寫 {mm.group(1)} 歲,時間線對本章事件的男主歲數是 {lo}' + (f'–{hi}' if hi != lo else '')))

    body_start = 3
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    body_lines = lines[body_start:]

    # E03 Markdown 污染、E04 場景分隔
    for i, ln in enumerate(body_lines, start=body_start + 1):
        s = ln.strip()
        if not s:
            continue
        if s != '＊' and (re.fullmatch(r'[*＊\-—─◇◆※・\s]{2,}', s) or s == '*'):
            errs.append(('E04', i, f'場景分隔應為單獨一行「＊」,而不是「{s}」'))
        elif re.match(r'(#{1,6}\s|[-*+]\s|\||\*\*|>|```)', s):
            errs.append(('E03', i, f'正文含 Markdown 標記:{s[:20]}'))

    body = '\n'.join(body_lines)

    # E05 規劃用語
    for pat, what in PLAN_PATTERNS:
        for mm in re.finditer(pat, body):
            ln = body[: mm.start()].count('\n') + body_start + 1
            errs.append(('E05', ln, f'正文出現{what}:「{mm.group(0)}」'))

    # E06 術語避免寫法
    for t in L.parse_terms():
        for bad in t['避免']:
            if bad and bad in body:
                ln = body[: body.index(bad)].count('\n') + body_start + 1
                errs.append(('E06', ln, f'使用「{bad}」,標準寫法為「{t["標準"]}」'))

    # E07 現代用詞
    for w in MODERN:
        mm = re.search(w, body)
        if mm:
            ln = body[: mm.start()].count('\n') + body_start + 1
            errs.append(('E07', ln, f'疑似現代用詞「{mm.group(0)}」(世界約唐宋,時間用時辰、更、晝夜、節令)'))

    # E08 稱謂禁用、W01 待決
    for r in L.naming_for(vol, n):
        for w in r['禁用']:
            if w and w in body:
                ln = body[: body.index(w)].count('\n') + body_start + 1
                errs.append(('E08', ln, f'稱謂表:{r["角色"]}此階段禁用「{w}」'))
        for w in r['待決']:
            w0 = re.sub(r'\(.*?\)', '', w)
            if w0 and w0 in body:
                warns.append(('W01', body[: body.index(w0)].count('\n') + body_start + 1,
                              f'「{w0}」的稱呼尚待決({r["角色"]},見待決單),確認是否有意使用'))

    # E09 揭露節點
    for r in L.reveals_blocked(vol, n):
        w = r['詞']
        if w in body:
            ln = body[: body.index(w)].count('\n') + body_start + 1
            msg = f'「{w}」最早到{L.chap_label(*r["first"])}才可出現({r["依據"]})'
            (errs if r['強度'] == '硬' else warns).append(('E09' if r['強度'] == '硬' else 'W02', ln, msg))

    # 場景卡禁揭詞(沒指定時,自動找 正文/計畫/{卷}/第NN章.場景卡.md)
    if not scene_card:
        auto = L.p('正文', '計畫', vol, f'第{n:02d}章.場景卡.md')
        if os.path.exists(auto):
            scene_card = auto
    if scene_card:
        sc = L.read(scene_card)
        for mm in re.finditer(r'^- \*?\*?禁揭詞\*?\*?:(.*)$', sc, re.M):
            for w in re.split(r'[、,，]', mm.group(1)):
                w = w.strip()
                if w and w not in ('無', '—') and w in body:
                    errs.append(('E10', body[: body.index(w)].count('\n') + body_start + 1, f'場景卡列為禁揭詞:「{w}」'))

    # 帳本
    lp = L.ledger_path(vol, n)
    if not os.path.exists(lp):
        if require_ledger:
            errs.append(('E11', 0, f'缺帳本:{L.rel(lp)}(見 正文/帳本/README.md)'))
    else:
        lg = L.parse_ledger(lp)
        for e in lg['errors']:
            errs.append(('E11', 0, f'帳本格式:{e}'))
        if '(待填' in lg['text']:
            errs.append(('E14', 0, '帳本仍有「(待填)」欄位,這是草稿,請補完'))
        if not lg['errors'] and o:
            cov = set()
            for r in lg['tables'].get('要點對照', []):
                for x in re.findall(r'\d+', r['要點']):
                    cov.add(int(x))
            missing = [k for k, _ in o['points'] if k not in cov]
            if missing:
                errs.append(('E11', 0, f'帳本「要點對照」缺大綱情節要點 {missing}'))
            for r in lg['tables'].get('新增事實', []):
                m2 = re.match(r'已回補→(.+)', r['回補'])
                if m2:
                    pth = m2.group(1).strip().split(';')[0].split('、')[0].strip()
                    if not L.exists(pth):
                        errs.append(('E12', 0, f'帳本回補路徑不存在:{pth}({r["ID"]})'))
            for r in lg['tables'].get('與大綱出入', []):
                mq = re.search(r'待決\((Q-\d+)\)', r['處置'])
                if mq and not L.exists(f'正文/待決/{mq.group(1)}.md'):
                    errs.append(('E12', 0, f'待決單不存在:{mq.group(1)}'))
            for r in lg['tables'].get('新增專名', []):
                nm = r['名稱']
                first = re.split(r'[、(（]', nm)[0].strip()
                if first and r['類型'] not in ('招式', '組織') and first not in body:
                    warns.append(('W03', 0, f'帳本新增專名「{first}」未在正文出現(帳本與正文不符?)'))

    # W04 已故者
    dead = set()
    prev = L.prev_chapter(vol, n)
    for lg in L.ledgers_before(vol, n):
        for r in lg['tables'].get('章末人物狀態', []):
            if '已故' in r['傷勢'] or '已故' in r['狀態']:
                dead.add(r['角色'])
    for d in sorted(dead):
        words = [d] + L.NAME_ALIASES.get(d, [])
        cnt = sum(body.count(w) for w in words if w)
        if cnt:
            warns.append(('W04', 0, f'已故者「{d}」出現 {cnt} 次(確認是回想、提及,而不是行動)'))

    # W05 未在大綱出現的已登記人名
    if o:
        outline_blob = o['text']
        alias_of = {}
        for canon, al in L.NAME_ALIASES.items():
            for x in al + [canon]:
                alias_of[x] = [canon] + al
        for nm in sorted(known_names(o)):
            group = alias_of.get(nm, [nm])
            if any(g in outline_blob for g in group):
                continue
            if nm in body and len(nm) >= 2:
                warns.append(('W05', 0, f'已登記人名「{nm}」出現 {body.count(nm)} 次,但不在本章大綱(確認是否合理)'))

    # W06 疑似新人名(說話標記前的稱呼)
    allow = known_names(o) if o else set()
    if o:
        allow |= set(re.findall(r'[一-鿿]{2,4}', o['text']))
    for lg in L.ledgers_before(vol, n):
        for r in lg['tables'].get('新增專名', []):
            allow |= set(re.split(r'[、(（]', r['名稱']))
    lp_cur = L.ledger_path(vol, n)
    if os.path.exists(lp_cur):
        for r in L.parse_ledger(lp_cur)['tables'].get('新增專名', []):
            allow |= set(re.split(r'[、(（]', r['名稱']))
    cand = {}
    for mm in re.finditer(r'(?:^|[。！？」，、；\s])([\u4e00-\u9fff]{2,3})(?:問道|說道|笑道|喝道|罵道|答道|嘆道|叫道|道)(?=[:：，,「])', body, re.M):
        w = mm.group(1)
        if w in PRONOUN_STOP or w in allow or any(w in a for a in allow) or w[-1] in '地著音聲氣的了' or w[0] in '用他她它':
            continue
        cand[w] = cand.get(w, 0) + 1
    if cand:
        top = '、'.join(f'{k}×{v}' for k, v in sorted(cand.items(), key=lambda t: -t[1])[:6])
        warns.append(('W06', 0, f'說話標記前出現未登記的稱呼:{top}(若是新人物,登記到帳本「新增專名」)'))

    # W10 名稱早於計畫首現(章節大綱的「出場角色」)。提示級:大綱可能漏列
    first = L.first_appearances()
    here = L.chap_key(vol, n)
    early = []
    for nm, rec in first.items():
        if nm not in body or len(nm) < 2:
            continue
        cast_at = rec['cast']
        mention_at = rec['mention']
        if o and nm in o['text']:
            continue
        planned = cast_at or mention_at
        if planned is not None and L.chap_key(*planned) > here:
            early.append(f'{nm}(計畫首現 {L.chap_label(*planned)})')
    if early:
        warns.append(('W10', 0, '名稱早於章節大綱安排的首現:' + '、'.join(early[:6]) + '(確認不是提前劇透;若是有意,先補章節大綱或開待決單)'))

    # W07 字數
    hz = L.han_count(body)
    if o:
        mb = re.search(r'([\d.]+)\s*萬', o['budget'])
        if mb:
            ratio = hz / (float(mb.group(1)) * 10000)
            if ratio < 0.45 or ratio > 1.1:
                warns.append(('W07', 0, f'漢字 {hz},約為大綱預計(含標點 {mb.group(1)} 萬)的 {int(ratio*100)}%(口徑見 Q-002;只供參考)'))

    # W08 套語與短段密度
    pats = {'不是…而是': r'不是[^。！？\n]{0,14}而是', '直到這時/那一刻': r'直到這時|那一刻|這一刻', '彷彿/仿佛': r'彷彿|仿佛', '忽然': r'忽然', '竟': r'竟'}
    rows = []
    for k, pat in pats.items():
        c = len(re.findall(pat, body))
        if c / max(hz, 1) * 1000 >= 1.6 and c >= 6:
            rows.append(f'{k}×{c}')
    if rows:
        warns.append(('W08', 0, '套語密度偏高:' + '、'.join(rows) + '(提示,見寫作規範第三節)'))
    paras = [p_ for p_ in body.split('\n') if p_.strip() and p_.strip() != '＊']
    short_run, worst = 0, 0
    for p_ in paras:
        if L.han_count(p_) <= 12 and not p_.strip().startswith('「'):
            short_run += 1
            worst = max(worst, short_run)
        else:
            short_run = 0
    if worst >= 5:
        warns.append(('W09', 0, f'連續 {worst} 個極短敘述段(提示;重要時刻的獨句成段是正常的)'))

    return errs, warns


def prose_all():
    return [f for v, c, t, f in L.prose_files()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*')
    ap.add_argument('--全部', action='store_true', dest='all')
    ap.add_argument('--場景卡')
    ap.add_argument('--不要帳本', action='store_true')
    ap.add_argument('--只看錯誤', action='store_true')
    a = ap.parse_args()
    files = prose_all() if a.all else [os.path.abspath(f) for f in a.files]
    if not files:
        ap.error('請指定檔案或 --全部')
    total_e = 0
    for f in files:
        errs, warns = check_file(f, require_ledger=not a.不要帳本, scene_card=a.場景卡)
        total_e += len(errs)
        print(f'## {L.rel(f)}:錯誤 {len(errs)},提示 {len(warns)}')
        for code, ln, msg in errs:
            print(f'  [{code}] {"行" + str(ln) + " " if ln else ""}{msg}')
        if not a.只看錯誤:
            for code, ln, msg in warns:
                print(f'  (提示 {code}) {"行" + str(ln) + " " if ln else ""}{msg}')
    sys.exit(1 if total_e else 0)


if __name__ == '__main__':
    main()
