#!/usr/bin/env python3
"""寫作工具的回歸測試:用植入錯誤的樣本確認 正文檢查 抓得到,並確認寫作包可重現、查詢不洩漏未來內容。

用法:python3 工具/測試.py        結束碼 0 = 全部通過
"""
import os
import re
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import 寫作庫 as L
import 正文檢查 as C
import 寫作包 as P

fails = []


def ok(cond, msg):
    if not cond:
        fails.append(msg)
        print('  失敗:' + msg)


def make(vol, n, title, body, head=None):
    d = tempfile.mkdtemp()
    dd = os.path.join(d, vol)
    os.makedirs(dd)
    o = L.get_outline(vol, n)
    head = head or f"# 第 {n} 章 · {title}\n\n> 視角:測試 ｜ 時間:測試 ｜ 對應事件:{'、'.join(o['events'])}\n\n"
    path = os.path.join(dd, f'第{n}章_{title}.md')
    with open(path, 'w', encoding='utf8') as f:
        f.write(head + body)
    return path


def codes(path, **kw):
    errs, warns = C.check_file(path, **kw)
    return {c for c, _, _ in errs}, {c for c, _, _ in warns}


print('1. 正文檢查:植入錯誤')
T1 = L.get_outline('第一部', 1)['title']
cases = [
    ('規劃用語外洩', '男主走進驛站,事件 P1-003 發生,他有 L12 的戰力。', {'E05'}),
    ('稱謂禁用(第一部第1章不得稱女主之名)', '知微蹲在馬腹旁。', {'E08'}),
    ('揭露節點(硬)', '那是高承嗣的人。岑照也來過。', {'E09'}),
    ('現代用詞', '他走了五公里,又等了三十分鐘。', {'E07'}),
    ('術語避免寫法', '他運起靈力,真氣在體內流轉。', {'E06'}),
    ('Markdown 污染', '**粗體** 的句子。\n\n- 條列\n', {'E03'}),
    ('場景分隔錯誤', '第一段。\n\n* * *\n\n第二段。', {'E04'}),
]
for name, body, expect in cases:
    path = make('第一部', 1, T1, body + '\n')
    e, w = codes(path, require_ledger=False)
    ok(expect <= e, f'{name}:應偵測 {expect},實得 {e}')

path = make('第一部', 1, T1, '正常的一段。\n', head='# 第 9 章 · 錯\n\n正文\n\n')
e, w = codes(path, require_ledger=False)
ok({'E01', 'E02'} <= e, f'標題與引言錯誤:應偵測 E01、E02,實得 {e}')

path = make('第一部', 1, T1, '老人說起秦七,七叔的墳在北邊。\n')
e, w = codes(path, require_ledger=False)
ok('W04' in w, f'已故者出現應有提示 W04,實得 {w}')

print('2. 正文檢查:定稿零錯誤')
for v, c, t, f in L.prose_files():
    e, w = codes(f)
    ok(not e, f'{v}第{c}章定稿不應有錯誤,實得 {e}')

print('3. 寫作包:可重現與預算')
a = P.build('第一部', 2)
b = P.build('第一部', 2)
ok(a == b, '同一狀態下兩次產生的寫作包應完全相同')
ok(re.search(r'輸入雜湊:[0-9a-f]{12}', a) is not None, '包頭應有輸入雜湊')
for key, title, size, lim in [(m[0], m[1], int(m[2]), int(m[3])) for m in re.findall(r'\| ([A-I]) \| ([^|]+) \| (\d+) \| (\d+)', a)]:
    if key not in ('B', 'I'):
        ok(size <= lim, f'寫作包 {key} 節超出預算 {size}>{lim}')
compact = P.build('第一部', 2, compact=True)
ok(len(compact) < len(a), '精簡包應比完整包短')

print('4. 劇透防火牆')
ok(not any(w in P.build('第一部', 2) for w in ['第三部結束']), '第一部寫作包不應引用「第三部結束」快照')
import subprocess
q = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), '查詢.py'), '阿古', '--至', '序1'],
                   capture_output=True, text=True).stdout
ok('序2' not in q and '序3' not in q and '一1' not in q, '查詢「--至 序1」不應包含序卷第 2 章之後的帳本記錄')
ok('設定·第一部' not in q and '記憶·第一部' not in q, '查詢不應包含未來卷的設定或記憶')

print('5. 導出檔最新')
for cmd in (['帳本合併.py', '--檢查'], ['建索引.py', '--檢查']):
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), cmd[0])] + cmd[1:],
                       capture_output=True, text=True)
    ok(r.returncode == 0, f'{cmd[0]} 導出檔過期:{r.stdout.strip()}')

print('6. 新增機制')
# E13:引言行年齡與時間線
path = make('第一部', 1, T1, '正常的一段。\n', head=f"# 第 1 章 · {T1}\n\n> 視角:陸懷川 30 歲 ｜ 時間:測試 ｜ 對應事件:{'、'.join(L.get_outline('第一部', 1)['events'])}\n\n")
e, w = codes(path, require_ledger=False)
ok('E13' in e, f'引言行年齡錯誤應偵測 E13,實得 {e}')
# W10:名稱早於計畫首現(高承嗣在第一部第 28 章才出場)
path = make('第一部', 1, T1, '他想起一個叫鄭成的人。\n')
first = L.first_appearances()
early = [n for n, r in first.items() if (r['cast'] or r['mention']) and L.chap_key(*(r['cast'] or r['mention'])) > L.chap_key('第一部', 1) and L.get_outline('第一部', 1)['text'].count(n) == 0]
if early:
    path = make('第一部', 1, T1, f'遠處傳來{early[0]}的名字。\n')
    e, w = codes(path, require_ledger=False)
    ok('W10' in w, f'名稱早於首現應有提示 W10({early[0]}),實得 {w}')
# E14:帳本草稿不能當正式帳本
import subprocess
here = os.path.dirname(os.path.abspath(__file__))
draft = subprocess.run([sys.executable, os.path.join(here, '帳本草稿.py'), '第一部', '1'], capture_output=True, text=True).stdout
ok('(待填' in draft and '## 要點對照' in draft, '帳本草稿應含 (待填) 與要點對照骨架')
# 盲測比對:同一份帳本比對自己 = 100%
real = L.rel(L.ledger_path('第一部', 1))
r = subprocess.run([sys.executable, os.path.join(here, '盲測比對.py'), real, real], capture_output=True, text=True)
ok('**100%**' in r.stdout, '同一份帳本互比應為 100% 一致')
# 其餘工具能跑完
for cmd in (['進度.py'], ['回補清單.py'], ['債務掃描.py'], ['聲口萃取.py', '--每人', '2'], ['影響掃描.py', '序卷', '3', '--每詞上限', '1'], ['寫作包.py', '第一部', '3', '--stdout']):
    r = subprocess.run([sys.executable, os.path.join(here, cmd[0])] + cmd[1:], capture_output=True, text=True)
    ok(r.returncode == 0 and r.stdout.strip(), f'{cmd[0]} 應能執行:{r.stderr.strip()[-120:]}')
# 全書 145 章的寫作包都能產生,且不超出預算
over, crashed = [], []
for o in L.all_outlines():
    try:
        txt = P.build(o['vol'], o['n'])
        for m in re.findall(r'\| ([A-I]) \| ([^|]+) \| (\d+) \| (\d+)(\(超出\))?', txt):
            if m[4]:
                over.append(f"{o['vol']}{o['n']}{m[0]}")
    except Exception as ex:  # noqa
        crashed.append(f"{o['vol']}{o['n']}:{ex!r}")
ok(not crashed, f'寫作包產生失敗:{crashed[:3]}')
ok(not over, f'寫作包超出預算:{over[:5]}')
ok('順序警告' in P.build('第一部', 5), '跳章時寫作包應有順序警告')
ok('順序警告' not in P.build('第一部', 2), '順序正確時不應有順序警告')
# 劇透防火牆:序卷與第一部的寫作包,A/C/D/E/G/H 節不得含本章尚不得出現的詞(硬級)
leaks = []
for o in L.all_outlines():
    if o['vol'] not in ('序卷', '第一部'):
        continue
    txt = P.build(o['vol'], o['n'])
    secs = re.split(r'\n## ([A-I])\. ', txt)
    d = {secs[i]: secs[i + 1] for i in range(1, len(secs) - 1, 2)}
    for r in L.reveals_blocked(o['vol'], o['n']):
        if r['強度'] != '硬':
            continue
        for k in 'ACDEGH':
            if r['詞'] in d.get(k, ''):
                leaks.append(f"{L.chap_label(o['vol'], o['n'])}/{k}/{r['詞']}")
ok(not leaks, f'寫作包洩漏尚不得出現的詞:{leaks[:6]}')
# 輸入雜湊要隨帳本內容改變
import copy
h1 = re.search(r'輸入雜湊:([0-9a-f]+)', P.build('第一部', 2)).group(1)
lp = L.ledger_path('第一部', 1)
orig = open(lp, encoding='utf8').read()
try:
    open(lp, 'w', encoding='utf8').write(orig.replace('未載', '未載(測試)', 1))
    h2 = re.search(r'輸入雜湊:([0-9a-f]+)', P.build('第一部', 2)).group(1)
finally:
    open(lp, 'w', encoding='utf8').write(orig)
ok(h1 != h2, '帳本內容改變時,寫作包的輸入雜湊應該跟著改變')
ok(h1 == re.search(r'輸入雜湊:([0-9a-f]+)', P.build('第一部', 2)).group(1), '還原後輸入雜湊應回到原值')
# 名字階梯(DEC-079):第 2 章可稱知微、不可稱溫知微;第 8 章起可稱溫知微
nm2 = {w for r in L.naming_for('第一部', 2) if r['角色'] == '女主' for w in r['禁用']}
nm8 = {w for r in L.naming_for('第一部', 8) if r['角色'] == '女主' for w in r['禁用']}
ok('溫知微' in nm2 and '知微' not in nm2, f'第一部第2章稱謂規則不符 DEC-079:禁用={nm2}')
ok(not nm8, f'第一部第8章起女主不應再有禁用稱呼:{nm8}')
# 場景卡覆蓋檢查
import 落稿 as W
problems, ns, npts = W.scene_card_problems('第一部', 2, '# 場景卡\n## 場景 1\n- 地點: x\n- 視角: x\n- 在場: x\n- 目的與衝突: x\n- 對應要點: 1\n- 揭露: x\n- 禁揭: x\n')
ok(any('沒有被任何場景涵蓋' in x for x in problems), '場景卡缺要點應被偵測')

if fails:
    print(f'\n{len(fails)} 項失敗')
    sys.exit(1)
print('\n全部測試通過')
