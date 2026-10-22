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

if fails:
    print(f'\n{len(fails)} 項失敗')
    sys.exit(1)
print('\n全部測試通過')
