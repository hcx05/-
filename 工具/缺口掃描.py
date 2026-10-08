#!/usr/bin/env python3
"""依凍結紀錄的出場者表掃描缺口(階段 B1)。用法:python3 工具/缺口掃描.py [卷名,預設 第一部]
列出尚無檔案的角色(含該卷設定)、勢力、場景;場景若已登記於場景設定 README 的「待建」清單則不算缺口。"""
import os, re, sys

sys.dont_write_bytecode = True


def read(p):
    with open(p, encoding='utf8') as f:
        return f.read()


def pending_scenes():
    """場景設定 README 中位於標題含「待建」之下的條目名稱。"""
    names, on = set(), False
    for line in read('世界設定/場景設定/README.md').split('\n'):
        if line.startswith('#'):
            on = '待建' in line
        elif on and line.startswith('- '):
            names.add(re.split(r'[(（:：]', line[2:].strip())[0].strip())
    return names


def scan(vol='第一部'):
    rows = []
    for line in read(f'故事線/{vol}/凍結.md').split('\n'):
        c = [x.strip() for x in line.strip('|').split('|')]
        if len(c) == 6 and re.fullmatch(r'P\d-\d+', c[0]):
            rows.append(c)
    uses = {'角色': {}, '勢力': {}, '場景': {}}
    for eid, _, _, roles, orgs, locs in rows:
        for kind, cell in (('角色', roles), ('勢力', orgs), ('場景', locs)):
            for n in cell.split('、'):
                if n and n != '—':
                    uses[kind].setdefault(n, []).append(eid)
    pend = pending_scenes()
    gaps = {'角色': [], '角色設定': [], '勢力': [], '場景': [], '待建場景': []}
    for n, ev in uses['角色'].items():
        root = f'角色/{n}' if n in ('男主', '女主') else f'角色/主要角色/{n}'
        if not os.path.isdir(root):
            gaps['角色'].append((n, ev))
        elif n not in ('男主', '女主') and not os.path.exists(f'{root}/設定/{vol}.md'):
            gaps['角色設定'].append((n, ev))
    for n, ev in uses['勢力'].items():
        if not os.path.exists(f'勢力/{n}.md'):
            gaps['勢力'].append((n, ev))
    for n, ev in uses['場景'].items():
        if os.path.exists(f'世界設定/場景設定/{n}/建模描述.md'):
            continue
        (gaps['待建場景'] if n in pend else gaps['場景']).append((n, ev))
    return uses, gaps


if __name__ == '__main__':
    vol = sys.argv[1] if len(sys.argv) > 1 else '第一部'
    uses, gaps = scan(vol)
    titles = {'角色': '缺角色資料夾', '角色設定': f'有資料夾但缺 設定/{vol}.md', '勢力': '缺勢力檔',
              '場景': '缺場景建模(且未登記待建)', '待建場景': '已登記為待建(不算缺口)'}
    for k, items in gaps.items():
        print(f'## {titles[k]}:{len(items)}')
        for n, ev in sorted(items, key=lambda x: -len(x[1])):
            print(f'- {n}({len(ev)} 個事件,首見 {ev[0]})')
    print(f'\n出場統計:角色 {len(uses["角色"])}、勢力 {len(uses["勢力"])}、場景 {len(uses["場景"])}')
