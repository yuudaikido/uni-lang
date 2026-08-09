#!/usr/bin/env python3
"""UNI 回帰マトリクス: examples/ の全プログラムを4ターゲットで実行し意味比較する。
必要環境: python3 / php / node / javac+java(任意。無いターゲットはスキップ)"""
import subprocess, re, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, 'examples')
UNI = os.path.join(ROOT, 'uni.py')

def norm(s):
    s = s.replace("'", '').replace('"', '').replace('None', 'null').replace('=', ':')
    s = re.sub(r'(\d+)\.0(?!\d)', r'\1', s)
    s = re.sub(r'\s+', '', s)
    return s

def run(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd).stdout

def main():
    targets = ['py']
    if shutil.which('php'): targets.append('php')
    if shutil.which('node'): targets.append('js')
    if shutil.which('javac') and shutil.which('java'): targets.append('java')
    progs = sorted(f for f in os.listdir(EX) if f.endswith('.nihongo') and f != 'test12.nihongo')
    allok = True
    for prog in progs:
        path = os.path.join(EX, prog)
        outs = {}
        for tgt in targets:
            code = run(f'python3 {UNI} {path} --target={tgt}', cwd=EX)
            if not code.strip():
                outs[tgt] = ''
                continue
            ext = {'py': 'py', 'php': 'php', 'js': 'js', 'java': 'java'}[tgt]
            fn = f'/tmp/uni_r.{ext}' if tgt != 'java' else '/tmp/Main.java'
            open(fn, 'w', encoding='utf-8').write(code)
            if tgt == 'py':   outs[tgt] = norm(run(f'python3 {fn}', cwd=EX))
            elif tgt == 'php': outs[tgt] = norm(run(f'php {fn}', cwd=EX))
            elif tgt == 'js':  outs[tgt] = norm(run(f'node {fn}', cwd=EX))
            else:
                run('javac -encoding UTF-8 /tmp/Main.java')
                outs[tgt] = norm(run('java -cp /tmp -Dstdout.encoding=UTF-8 Main', cwd=EX))
        base = outs.get('py', '')
        bad = [t for t in outs if outs[t] != base] if base.strip() else ['py空']
        print(f'{prog}:', '✅' if not bad else f'❌ {bad}')
        if bad: allok = False
    print('総合:', '✅ 全通過' if allok else '❌ 要修正')
    sys.exit(0 if allok else 1)

if __name__ == '__main__':
    main()
