"""统计项目代码数：逐级递归展示，含文件夹汇总和文件类型统计。"""

import os

STATS_DIR = os.path.dirname(os.path.abspath(__file__))
IGNORE_DIRS = {'.git', '__pycache__', '.venv', 'log', '.sisyphus', '.trae', 'node_modules'}
IGNORE_FILES = {'index.json', 'package-lock.json'}


def vis_len(s):
    """中文字符算 2 宽度，其余算 1。"""
    return sum(2 if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f' else 1 for c in s)


def vis_ljust(s, w):
    """按视觉宽度左对齐。"""
    return s + ' ' * max(0, w - vis_len(s))


def vis_rjust(s, w):
    """按视觉宽度右对齐。"""
    return ' ' * max(0, w - vis_len(s)) + s


def is_text(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in {'.py', '.js', '.css', '.html', '.json', '.yaml', '.yml',
                   '.md', '.txt', '.cfg', '.ini', '.toml', '.spec', '.jsonl'}


def gather(path):
    items = []
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return items
    for e in entries:
        fp = os.path.join(path, e)
        if os.path.isdir(fp):
            if e in IGNORE_DIRS:
                continue
            sub = gather(fp)
            if sub or any(os.path.isfile(os.path.join(fp, f)) for f in os.listdir(fp)):
                items.append(('dir', e, sub))
        else:
            if e in IGNORE_FILES or e.startswith('.'):
                continue
            try:
                sz = os.path.getsize(fp)
            except OSError:
                sz = 0
            lines = 0
            if is_text(e):
                try:
                    with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                        lines = sum(1 for _ in f)
                except Exception:
                    pass
            items.append(('file', e, sz, lines))
    return items


def _count_sub(lst):
    files = bytes_ = lines_ = 0
    for x in lst:
        if x[0] == 'file':
            files += 1
            bytes_ += x[2]
            lines_ += x[3]
        elif x[0] == 'dir':
            f, b, l = _count_sub(x[2])
            files += f
            bytes_ += b
            lines_ += l
    return files, bytes_, lines_


def print_tree(items, prefix=''):
    entries = [('d', x[1]) if x[0] == 'dir' else ('f', x[1]) for x in items]
    last_idx = len(entries) - 1 if entries else -1

    type_stats = {}  # ext -> (count, bytes, lines)

    for idx, item in enumerate(items):
        is_last = (idx == last_idx) and (last_idx >= 0)
        connector = '└── ' if is_last else '├── '

        if item[0] == 'dir':
            _, name, sub = item
            d_files, d_bytes, d_lines = _count_sub(sub)
            sub_prefix = prefix + ('    ' if is_last else '│   ')
            print(f'{prefix}{connector}{name}/  ({d_files} 个文件, {d_lines} 行, {d_bytes} 字节)')
            sub_types = print_tree(sub, sub_prefix)
            for ext, v in sub_types.items():
                t, b, l = type_stats.get(ext, (0, 0, 0))
                type_stats[ext] = (t + v[0], b + v[1], l + v[2])
        else:
            _, name, sz, lines = item
            ext = os.path.splitext(name)[1].lower() or '(无扩展名)'
            t, b, l = type_stats.get(ext, (0, 0, 0))
            type_stats[ext] = (t + 1, b + sz, l + lines)
            print(f'{prefix}{connector}{name}  ({lines} 行, {sz} 字节)')

    return type_stats


def main():
    data = gather(STATS_DIR)
    print()
    type_stats = print_tree(data)

    # 文件类型统计
    print()
    print('=' * 60)
    total_files = sum(v[0] for v in type_stats.values())
    total_bytes = sum(v[1] for v in type_stats.values())
    total_lines = sum(v[2] for v in type_stats.values())
    print(f'总计: {total_files} 个文件, {total_lines} 行, {total_bytes} 字节')

    print()
    print('─' * 48)
    print('文件类型统计:')
    print(f'{vis_ljust("扩展名", 20)} {vis_rjust("数量", 6)} {vis_rjust("行数", 8)} {vis_rjust("字节", 10)}')
    print('─' * 48)
    for ext in sorted(type_stats, key=lambda e: -type_stats[e][2]):
        cnt, byt, lin = type_stats[ext]
        print(f'{vis_ljust(ext, 20)} {vis_rjust(str(cnt), 6)} {vis_rjust(str(lin), 8)} {vis_rjust(str(byt), 10)}')
    print('─' * 48)
    print(f'{vis_ljust("总计", 20)} {vis_rjust(str(total_files), 6)} {vis_rjust(str(total_lines), 8)} {vis_rjust(str(total_bytes), 10)}')
    print()


if __name__ == '__main__':
    main()
