#!/usr/bin/env python3
# UNI English frontend (v0.4): translation table only — the parser is untouched.
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uni import Parser, BACKENDS

SIGILS = [
    (r'\\\$(\w+)', r'￥「\1'),
    (r'\$(\w+)',   r'「\1'),
    (r"'([^']*)'", r'’\1’'),
]
MARKERS = [
    (r'(\S+)\s+\babove\b\s+(\S+)', r'\1 \2より大きい'),
    (r'(\S+)\s+\bbelow\b\s+(\S+)', r'\1 \2より小さい'),
    (r'\bfrom\s+(\S+)', r'\1から'),
    (r'\bto\s+(\S+)',   r'\1まで'),
    (r'\bby\s+(\S+)',   r'\1ずつ'),
    (r'\bas\s+(「\S+)', r'\1が'),
]
VERBS = [
    (r'\bup\b',   'ふえる'), (r'\bdown\b', 'へる'),
    (r'(^|\s)(.*?)\badd\s+(\S+)',  r'\1\2 \3 足す'),
    (r'\bgive\s+(\S+)', r'\1渡す'),
    (r'\bshow\s+(.+?)(?=。|$)', r'\1 出す'),
    (r'\bfinally\b', '最後に'),
    (r'\bdefine\b',  '定義'),
]
PUNCT = [ (r'\.(\s|$)', r'。\1'), (r',', '、') ]
DIGITS = []

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
    tgt = 'py'
    for a in sys.argv[1:]:
        if a.startswith('--target='): tgt = a.split('=')[1]
    print(BACKENDS[tgt](colls).render(ir))
