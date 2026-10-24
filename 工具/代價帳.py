#!/usr/bin/env python3
"""代價帳量測(劇情基準 J 組)。讀 狀態/代價帳.md,回答「主角的損失在全書怎麼分布」。

用法:
  python3 工具/代價帳.py            # 量測報告(只是提示,結束碼恆為 0,格式錯誤除外)
  python3 工具/代價帳.py --strict   # 帳本格式有錯則結束碼為 1(J1 超出門檻只是提示,不影響結束碼)

量測:
  J1 最長「主角沒有不可逆損失」的連續章數(以全書章序計;男女主任一承擔即算有損失)
  J2 重類(標籤帶死亡、悲劇)演出事件的帳目覆蓋率;列出尚無帳目的候選
  J3 主角損失的類別與可逆性分布
帳本由人(或 LLM)依事件描述填寫,覆蓋不全時 J1 會偏高;J2 的候選清單就是用來稽核覆蓋的。
基準區間讀 設計規範/劇情基準.md 的「基準區間(機器讀取)」,J1 為專案自訂,尚未用外部作品校準。
"""
import collections, os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 劇情量化 as Q

LEDGER = '狀態/代價帳.md'
CATEGORIES = ('生命', '亡故', '身體', '關係', '處境', '能力', '地位', '良心', '取捨')
REVERSIBILITY = ('不可逆', '部分', '可逆')
LEADS = ('男主', '女主')
HEAVY_TAGS = ('死亡', '悲劇')


def load_ledger():
    rows = []
    text = Q.read(LEDGER)
    m = re.search(r'## 帳目\n(.*?)(?=\n## |\Z)', text, re.S)
    for c in Q.table(m.group(1) if m else ''):
        if len(c) >= 6 and Q.ID.fullmatch(c[0]):
            rows.append({'id': c[0], 'who': c[1], 'cat': c[2], 'loss': c[3], 'rev': c[4], 'src': c[5]})
    return rows


def problems(rows=None, tl=None, ev=None):
    """格式與引用檢查:事件須存在、類別與可逆性須在詞表內、承擔者須是出場者或註明不在場。"""
    if rows is None:
        rows = load_ledger()
    if tl is None:
        tl, ev, _, _ = Q.load_all()
    known = {r['id'] for v in Q.VOLS for r in tl[v]}
    cast = {}
    for v in Q.VOLS:
        for eid, e in ev[v].items():
            cast[eid] = set(e['chars'])
    out = []
    if not rows:
        out.append(f'{LEDGER} 沒有帳目')
    seen = set()
    for r in rows:
        tag = f"{r['id']} {r['who']}"
        if r['id'] not in known:
            out.append(f'{tag}:事件不在時間線')
        if r['cat'] not in CATEGORIES:
            out.append(f"{tag}:類別「{r['cat']}」不在詞表 {'、'.join(CATEGORIES)}")
        if r['rev'] not in REVERSIBILITY:
            out.append(f"{tag}:可逆性「{r['rev']}」須為 {'、'.join(REVERSIBILITY)}")
        if not r['loss'] or not r['src']:
            out.append(f'{tag}:損失與依據不可空白')
        key = (r['id'], r['who'], r['cat'])
        if key in seen:
            out.append(f'{tag}:重複帳目({r["cat"]})')
        seen.add(key)
        if r['id'] in cast and r['who'] not in cast[r['id']] and '不在場' not in r['src']:
            out.append(f'{tag}:承擔者不在事件出場者中(若確為不在場者承擔,依據欄須寫「不在場」)')
    return out


def chapter_of(tl_index, eid):
    r = tl_index.get(eid)
    return (r['vol'], r['ch'], r['kind']) if r else None


def runs_without(chs, total):
    """chs:有損失的全書章序集合;回傳最長的無損失連續區間 (長度, 起, 迄)。"""
    best, start = (0, 0, 0), 1
    for g in sorted(chs) + [total + 1]:
        if g - start > best[0]:
            best = (g - start, start, g - 1)
        start = g + 1
    return best


def label(g):
    for v in reversed(Q.VOLS):
        if g > Q.OFF[v]:
            return f'{v} 第 {g - Q.OFF[v]} 章'
    return str(g)


def main(argv):
    strict = '--strict' in argv
    tl, ev, ci, pos = Q.load_all()
    tt = Q.tag_types()
    bm = Q.bench()
    rows = load_ledger()
    probs = problems(rows, tl, ev)
    index = {r['id']: r for v in Q.VOLS for r in tl[v]}
    total = sum(Q.chapter_count(v) for v in Q.VOLS)

    print('代價帳量測(劇情基準 J 組)\n')
    print(f'帳目 {len(rows)} 筆,涉及事件 {len({r["id"] for r in rows})} 個,承擔者 {len({r["who"] for r in rows})} 人。')
    if probs:
        print(f'\n格式問題 {len(probs)} 項:')
        for p in probs:
            print('  ✗', p)

    # J1
    print('\n[J1] 主角沒有損失的最長連續章數(全書 %d 章;背景與未排章的事件不計入章序)' % total)

    def lead_chapters(who, revs):
        s = set()
        for r in rows:
            if r['who'] in who and r['rev'] in revs and r['id'] in index:
                v, ch, kind = chapter_of(index, r['id'])
                if ch > 0:
                    s.add(Q.gidx(v, ch))
        return s

    for name, who, revs in (('男女主任一,不可逆', LEADS, ('不可逆',)),
                            ('男女主任一,不可逆或部分', LEADS, ('不可逆', '部分')),
                            ('男主,不可逆', ('男主',), ('不可逆',)),
                            ('女主,不可逆', ('女主',), ('不可逆',))):
        n, a, b = runs_without(lead_chapters(who, revs), total)
        j = Q.judge('J1', n, bm) if name == '男女主任一,不可逆' else ''
        print(f'  {name}:最長 {n} 章({label(a)} 至 {label(b)}){" " + j if j else ""}')

    # J2
    print('\n[J2] 重類(死亡、悲劇)演出事件的帳目覆蓋')
    covered = {r['id'] for r in rows}
    heavy = [r for v in Q.VOLS for r in tl[v] if r['kind'] == '演出' and set(r['tags']) & set(HEAVY_TAGS)]
    miss = [r for r in heavy if r['id'] not in covered]
    covered_ch = {(index[i]['vol'], index[i]['ch']) for i in covered if i in index}
    chain = [r for r in miss if (r['vol'], r['ch']) in covered_ch]
    bare = [r for r in miss if (r['vol'], r['ch']) not in covered_ch]
    print(f'  {len(heavy) - len(miss)}/{len(heavy)} 有帳目(%.0f%%)' % (100 * (len(heavy) - len(miss)) / max(1, len(heavy))))
    for title, group in (('整章都沒有帳目(優先檢視;事件描述若明文寫到損失才補,沒有就不補)', bare),
                         ('同章已有帳目(多半是同一事件鏈,可不補)', chain)):
        if group:
            print(f'  {title}:')
            for r in group:
                print(f"    {r['id']} {r['vol']}第 {r['ch']} 章 [{'、'.join(r['tags'])}] {r['name']}")

    # J3
    print('\n[J3] 男女主損失的類別與可逆性')
    lead_rows = [r for r in rows if r['who'] in LEADS]
    by = collections.Counter((r['cat'], r['rev']) for r in lead_rows)
    for cat in CATEGORIES:
        parts = [f'{rev} {by[(cat, rev)]}' for rev in REVERSIBILITY if by[(cat, rev)]]
        if parts:
            print(f'  {cat}:' + '、'.join(parts))
    per_vol = collections.Counter()
    for r in lead_rows:
        if r['id'] in index and r['rev'] == '不可逆':
            per_vol[index[r['id']]['vol']] += 1
    print('  各卷男女主不可逆損失筆數:' + '、'.join(f'{v} {per_vol[v]}' for v in Q.VOLS))

    print('\n說明:帳本是依事件描述手填的草案,覆蓋不全會讓 J1 偏高;J1 上限為專案自訂,未用外部作品校準。結果只是提示。')
    if strict and probs:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
