#!/usr/bin/env python3
"""落稿:把模型依「交付格式」(手冊/提示/落稿格式.md)輸出的區塊,存成場景稿、組成整章、寫入帳本與待決單。

用法:
    python3 工具/落稿.py 場景 第一部 2 3 模型輸出.txt     # 存第 3 場;檔名用 - 表示從標準輸入讀
    python3 工具/落稿.py 組稿 第一部 2                     # 把已存的場景稿組成 正文/第一部/第2章_標題.md 並檢查
    python3 工具/落稿.py 帳本 第一部 2 模型輸出.txt        # 存帳本、驗證格式、重建累積狀態與索引
    python3 工具/落稿.py 待決 模型輸出.txt                 # 存待決單(自動編號)
    python3 工具/落稿.py 場景卡 第一部 2 場景卡.md         # 檢查場景卡是否涵蓋大綱每個情節要點

場景稿放在 正文/計畫/{卷}/第NN章/場景NN.md(未定稿的工作檔)。
"""
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 寫作庫 as L


def read_input(arg):
    if arg == '-':
        return sys.stdin.read()
    with open(arg, encoding='utf8') as f:
        return f.read()


def blocks(text):
    """解析 =====名稱===== 區塊 → {名稱: 內容}。"""
    out, name, buf = {}, None, []
    for ln in text.split('\n'):
        m = re.fullmatch(r'\s*=====\s*(.+?)\s*=====\s*', ln)
        if m:
            if name is not None:
                out[name] = '\n'.join(buf).strip('\n')
            name, buf = m.group(1), []
        elif name is not None:
            buf.append(ln)
    if name is not None:
        out[name] = '\n'.join(buf).strip('\n')
    return out


def scene_dir(vol, n):
    return L.p('正文', '計畫', vol, f'第{n:02d}章')


def refresh():
    for script, args in (('帳本合併.py', []), ('建索引.py', [])):
        subprocess.run([sys.executable, os.path.join(HERE, script)] + args, check=True)


def cmd_scene(vol, n, k, src):
    b = blocks(read_input(src))
    if '正文' not in b or not b['正文'].strip():
        raise SystemExit('輸出裡沒有「=====正文=====」區塊')
    body = b['正文'].strip() + '\n'
    bad = [ln for ln in body.split('\n') if re.match(r'\s*(#|>|\*\*|---|- )', ln)]
    if bad:
        raise SystemExit(f'場景正文含 Markdown 標記,請修正:{bad[0][:30]}')
    d = scene_dir(vol, n)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f'場景{k:02d}.md'), 'w', encoding='utf8') as f:
        f.write(body)
    if '場景末狀態' in b:
        with open(os.path.join(d, f'場景{k:02d}.末狀態.md'), 'w', encoding='utf8') as f:
            f.write(b['場景末狀態'].strip() + '\n')
    print(f'已存 {L.rel(os.path.join(d, f"場景{k:02d}.md"))}({L.han_count(body)} 漢字)')


def cmd_assemble(vol, n):
    o = L.get_outline(vol, n)
    if not o:
        raise SystemExit('找不到章節大綱')
    d = scene_dir(vol, n)
    files = sorted(f for f in os.listdir(d) if re.fullmatch(r'場景\d+\.md', f)) if os.path.isdir(d) else []
    if not files:
        raise SystemExit(f'{L.rel(d)} 沒有場景稿')
    parts = [L.read(os.path.join(d, f)).strip() for f in files]
    head = f"# 第 {n} 章 · {o['title']}\n\n> 視角:{o['pov']} ｜ 時間:{o['time']} ｜ 對應事件:{'、'.join(o['events'])}\n\n"
    text = head + '\n\n＊\n\n'.join(parts) + '\n'
    out = L.p('正文', vol, f"第{n}章_{o['title']}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf8') as f:
        f.write(text)
    print(f'已組成 {L.rel(out)}({len(files)} 場,{L.han_count(text)} 漢字)。接著檢查:')
    subprocess.run([sys.executable, os.path.join(HERE, '正文檢查.py'), out, '--不要帳本'])
    print('提醒:引言行的「視角」「時間」是從大綱照抄的,請改成貼合正文的寫法(例:懷川(12 歲)、後 12 年臘月初七)。')


def cmd_ledger(vol, n, src):
    b = blocks(read_input(src))
    if '帳本' not in b:
        raise SystemExit('輸出裡沒有「=====帳本=====」區塊')
    path = L.ledger_path(vol, n)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf8') as f:
        f.write(b['帳本'].strip() + '\n')
    lg = L.parse_ledger(path)
    if lg['errors']:
        print('帳本格式有問題(已存檔,請修正後重跑):')
        for e in lg['errors']:
            print('  - ' + e)
        sys.exit(1)
    refresh()
    print(f'已存 {L.rel(path)},累積狀態與索引已重建')


def cmd_decision(src):
    b = blocks(read_input(src))
    if '待決' not in b:
        raise SystemExit('輸出裡沒有「=====待決=====」區塊')
    d = L.p('正文', '待決')
    nums = [int(m.group(1)) for f in os.listdir(d) for m in [re.match(r'Q-(\d+)\.md', f)] if m]
    q = f'Q-{(max(nums) + 1 if nums else 1):03d}'
    fields = {}
    for ln in b['待決'].split('\n'):
        m = re.match(r'(標題|影響範圍|雙方出處|暫行做法|建議選項)\s*[:：]\s*(.*)', ln)
        if m:
            fields[m.group(1)] = m.group(2)
    body = f"# {q} {fields.get('標題', '(未命名)')}\n\n- **狀態**:待決\n- **影響範圍**:{fields.get('影響範圍', '')}\n- **雙方出處**:{fields.get('雙方出處', '')}\n- **暫行做法**:{fields.get('暫行做法', '')}\n- **建議選項**:{fields.get('建議選項', '')}\n"
    with open(os.path.join(d, f'{q}.md'), 'w', encoding='utf8') as f:
        f.write(body)
    print(f'已存 正文/待決/{q}.md;請同步更新 正文/待決/README.md 的清單')


def scene_card_problems(vol, n, text):
    """回傳 (問題清單, 場景數, 要點數)。"""
    o = L.get_outline(vol, n)
    scenes = re.split(r'\n(?=## 場景\s*\d+)', text)[1:]
    if not scenes:
        return ['場景卡需要「## 場景 N」區段'], 0, len(o['points'])
    covered = set()
    problems = []
    for sc in scenes:
        head = sc.split('\n', 1)[0]
        m = re.search(r'^- \*?\*?對應要點\*?\*?:(.*)$', sc, re.M)
        if not m:
            problems.append(f'{head} 缺「對應要點」')
            continue
        for x in re.findall(r'\d+', m.group(1)):
            covered.add(int(x))
        for key in ('地點', '視角', '在場', '目的與衝突', '揭露', '禁揭'):
            if not re.search(rf'^- \*?\*?{key}\*?\*?:', sc, re.M):
                problems.append(f'{head} 缺「{key}」')
    missing = [k for k, _ in o['points'] if k not in covered]
    if missing:
        problems.append(f'大綱情節要點 {missing} 沒有被任何場景涵蓋')
    return problems, len(scenes), len(o['points'])


def cmd_scene_card(vol, n, src):
    problems, ns, npts = scene_card_problems(vol, n, read_input(src))
    if problems:
        print('場景卡有問題:')
        for p_ in problems:
            print('  - ' + p_)
        sys.exit(1)
    print(f'場景卡通過:{ns} 個場景涵蓋全部 {npts} 個情節要點')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    cmd = a[0]
    if cmd == '場景' and len(a) == 5:
        cmd_scene(a[1], int(a[2]), int(a[3]), a[4])
    elif cmd == '組稿' and len(a) == 3:
        cmd_assemble(a[1], int(a[2]))
    elif cmd == '帳本' and len(a) == 4:
        cmd_ledger(a[1], int(a[2]), a[3])
    elif cmd == '待決' and len(a) == 2:
        cmd_decision(a[1])
    elif cmd == '場景卡' and len(a) == 4:
        cmd_scene_card(a[1], int(a[2]), a[3])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
