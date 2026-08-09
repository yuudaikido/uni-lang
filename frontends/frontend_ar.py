#!/usr/bin/env python3
# UNI アラビア語フロントエンド: 右書き(RTL)文字・アラビア数字での対応表検証
# 論点: 表示は右書きでも、コードポイント列は論理順 → 対応表方式が通るか
import re, sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uni import Parser, BACKENDS

SIGILS = [
    (r'\\\$(\w+)', r'￥「\1'),
    (r'\$([\w\u0600-\u06FF]+)', r'「\1'),
    (r"'([^']*)'", r'’\1’'),
]
DIGITS = [(chr(0x0660+i), str(i)) for i in range(10)]   # ٠١٢٣… → 0123…
# 教訓: 前置マーカーは語境界(\b)必須+長い句を先に(部分文字列衝突の回避)
MARKERS = [
    (r'(\S+)\s*\bأكبر\s+من\b\s*(\S+)', r'\1 \2より大きい'),   # 複合句を先に
    (r'\bمن\b\s*(\S+)', r'\1から'),
    (r'\bإلى\b\s*(\S+)', r'\1まで'),
    (r'\bكل\b\s*(\S+)', r'\1ずつ'),
    (r'\bلـ\s*(「\S+)', r'\1が'),
]
VERBS = [
    (r'تزايد', 'ふえる'),
    (r'(^|\s)(.*?)أضف\s*(\S+)', r'\1\2 \3 足す'),      # أضف = 足す(add)
    (r'أرجع\s*(\S+)', r'\1渡す'),                       # أرجع = 渡す(return)
    (r'اطبع\s*(.+?)(?=。|\.|$)', r'\1 出す'),           # اطبع = 出す(print)
    (r'أخيرا', '最後に'),
    (r'عرف', '定義'),                                    # عرف = 定義(define)
]
PUNCT = [(r'،', '、'), (r'؛', '；'), (r'\.(\s|$)', r'。\1')]

def to_canonical(src):
    lines = []
    for line in src.split('\n'):
        for a, b in DIGITS:
            line = line.replace(a, b)
        for pat, rep in SIGILS + PUNCT + MARKERS + VERBS:
            line = re.sub(pat, rep, line)
        lines.append(line)
    return '\n'.join(lines)

if __name__ == '__main__':
    src = open(sys.argv[1], encoding='utf-8').read()
    canonical = to_canonical(src)
    if '--show-canonical' in sys.argv:
        print('--- canonical ---'); print(canonical); print('--- output ---')
    p = Parser()
    ir, colls = p.parse(canonical)
    if p.errors:
        print('\n'.join(p.errors), file=sys.stderr); sys.exit(1)
    print(BACKENDS['py'](colls).render(ir))
