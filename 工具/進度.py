#!/usr/bin/env python3
"""進度:一眼看出寫到哪、下一章是什麼、有什麼阻礙。新接手的模型或人先跑這個。

用法:
    python3 工具/進度.py                # 各卷進度 + 下一章 + 阻礙 + 建議指令
    python3 工具/進度.py 第一部          # 逐章列出該卷每一章的階段
階段:無 → 場景卡 → 場景稿(k) → 成稿(缺帳本) → 完成
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L


def stage(vol, n):
    has_prose = L.prose_path(vol, n) is not None
    has_ledger = os.path.exists(L.ledger_path(vol, n))
    card = os.path.exists(L.p('正文', '計畫', vol, f'第{n:02d}章.場景卡.md'))
    sd = L.p('正文', '計畫', vol, f'第{n:02d}章')
    scenes = len([f for f in os.listdir(sd) if re.fullmatch(r'場景\d+\.md', f)]) if os.path.isdir(sd) else 0
    if has_prose and has_ledger:
        return '完成'
    if has_prose:
        return '成稿(缺帳本)'
    if scenes:
        return f'場景稿({scenes})'
    if card:
        return '場景卡'
    return '無'


def pending_backfill():
    n = 0
    for v, c, f in L.ledger_files():
        lg = L.parse_ledger(f)
        for r in lg['tables'].get('新增事實', []):
            if r['回補'].startswith('待回補'):
                n += 1
    return n


def main():
    outs = L.all_outlines()
    if len(sys.argv) > 1 and sys.argv[1] in L.VOLS:
        v = sys.argv[1]
        for o in outs:
            if o['vol'] == v:
                print(f"{L.chap_label(v, o['n']):>5}  {o['title']:<10} {stage(v, o['n'])}")
        return
    print('# 進度\n')
    print('| 卷 | 章數 | 完成 | 進行中 | 未開始 |')
    print('|---|---|---|---|---|')
    nxt = []
    for v in L.VOLS:
        vo = [o for o in outs if o['vol'] == v]
        st = [stage(v, o['n']) for o in vo]
        done = st.count('完成')
        todo = st.count('無')
        print(f'| {v} | {len(vo)} | {done} | {len(vo) - done - todo} | {todo} |')
        for o, s_ in zip(vo, st):
            if s_ != '完成':
                nxt.append((v, o, s_))
    if not nxt:
        print('\n全書完成。')
        return
    v, o, s_ = nxt[0]
    print(f"\n**下一章**:{v}第 {o['n']} 章〈{o['title']}〉— 目前階段:{s_}")
    print(f"- 大綱:{o['path']}(對應事件 {'、'.join(o['events'])};預計字數 {o['budget']})")
    if len(nxt) > 1:
        print('- 之後:' + '、'.join(f"{x[0]}{x[1]['n']}〈{x[1]['title']}〉" for x in nxt[1:4]))

    print('\n## 阻礙與注意')
    blockers = 0
    for q in L.open_questions():
        if q['狀態'].startswith('待'):
            blockers += 1
            hit = '(影響範圍提到下一章)' if re.search(rf"第 ?{o['n']} ?(章|至)", q['影響']) else ''
            print(f"- 待決 {q['標題']}{hit}。暫行:{L.truncate(q['暫行'], 70, '…')}")
    back = pending_backfill()
    if back:
        blockers += 1
        print(f'- 帳本中有 {back} 條「待回補」的新增事實(`python3 工具/回補清單.py` 查看)')
    patches = [h for h in o['sections'] if re.search(r'增補|改版|對齊|DEC-\d+', h)]
    if patches:
        blockers += 1
        print(f"- 下一章大綱含補丁段落:{'、'.join(patches)}(以補丁為準,寫作包 B 節已前置)")
    here = os.path.dirname(os.path.abspath(__file__))
    import subprocess
    for script, label in (('帳本合併.py', '累積狀態'), ('建索引.py', '索引')):
        r = subprocess.run([sys.executable, os.path.join(here, script), '--檢查'], capture_output=True, text=True)
        if r.returncode != 0:
            blockers += 1
            print(f'- 導出檔「{label}」已過期:先執行 python3 工具/{script}')
    if not blockers:
        print('- (無)')

    print('\n## 建議的下一步')
    cmds = {
        '無': f'python3 工具/寫作包.py {v} {o["n"]}      # 取包,讀完後寫場景卡 正文/計畫/{v}/第{o["n"]:02d}章.場景卡.md',
        '場景卡': f'python3 工具/落稿.py 場景卡 {v} {o["n"]} 正文/計畫/{v}/第{o["n"]:02d}章.場景卡.md   # 通過後逐場景生成',
        '成稿(缺帳本)': f'python3 工具/帳本草稿.py {v} {o["n"]}   # 產生帳本草稿,填完用 落稿.py 帳本 存入',
    }
    print(cmds.get(s_, f'接續場景稿:python3 工具/落稿.py 場景 {v} {o["n"]} {{下一場景號}} 輸出.txt;全部場景寫完後 python3 工具/落稿.py 組稿 {v} {o["n"]}'))
    print('流程全貌:手冊/生成手冊.md')


if __name__ == '__main__':
    main()
