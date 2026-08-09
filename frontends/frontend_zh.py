#!/usr/bin/env python3
# UNI 中国語フロントエンド: 対応表のみでパーサ無変更(英語版と同方式)
# 中国語の特性検証: 無活用・SVO・前置マーカー・句読点「。」「，」共有
import re, sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uni import Parser, BACKENDS, php_join_else

SIGILS = [
    (r'\\\$(\w+)', r'￥「\1'),
    (r'\$(\w+)',   r'「\1'),
    (r"'([^']*)'", r'’\1’'),
]
MARKERS = [
    (r'从\s*(\S+)', r'\1から'),          # 从1 → 1から
    (r'到\s*(\S+)', r'\1まで'),          # 到3 → 3まで
    (r'每\s*(\S+)', r'\1ずつ'),          # 每1 → 1ずつ
    (r'令\s*(「\S+)', r'\1が'),          # 令$I → 「Iが
    (r'(\S+)\s*大于\s*(\S+)', r'\1 \2より大きい'),
    (r'(\S+)\s*小于\s*(\S+)', r'\1 \2より小さい'),
]
VERBS = [
    (r'递增', 'ふえる'), (r'递减', 'へる'),
    (r'(^|\s)(.*?)加\s*(\S+)', r'\1\2 \3 足す'),
    (r'返\s*(\S+)', r'\1渡す'),
    (r'出\s*(.+?)(?=。|$)', r'\1 出す'),
    (r'最后', '最後に'),
    (r'定义', '定義'),
]
PUNCT = [(r'，', '、'), (r',', '、')]

def to_canonical(src):
    lines = []
    for line in src.split('\n'):
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
    print(BACKENDS['py'](colls).render(ir))
