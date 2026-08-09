#!/usr/bin/env python3
# UNI 文法コアv0.3 トランスパイラ第2世代
# 構造: パーサ → 中立IR → バックエンド(Python / PHP)
# 二面投影の右側(出力側)を複数化する実証。パーサはターゲットを一切知らない。
import re, sys, unicodedata

# ================= 正規化・前処理(v1と同一) =================
def normalize(src):
    out = []
    for ch in src:
        out.append(ch if ch in '、。「」’￥；' else unicodedata.normalize('NFKC', ch))
    s = ''.join(out).replace('¥', '￥').replace('−', '-').replace('－', '-')
    KD = dict(zip('〇一二三四五六七八九', '0123456789'))
    def _kconv(m):
        w = m.group(0)
        w = ''.join(KD.get(c, c) for c in w)
        w = re.sub(r'(\d)十(\d)', r'\1\2', w)
        w = re.sub(r'(\d)十', r'\g<1>0', w)
        w = re.sub(r'十(\d)', r'1\1', w)
        return w.replace('十', '10')
    # 漢数字の変換は文脈限定: ①個目/つ目/番目の直前 ②他の漢字・かなに隣接しない単独
    s = re.sub(r'[〇一二三四五六七八九十]+(?=(?:個|つ|番)目)', _kconv, s)
    s = re.sub(r'(?<![\u3040-\u30FF\u4E00-\u9FFF])[〇一二三四五六七八九十]+(?![\u3040-\u30FF\u4E00-\u9FFF])', _kconv, s)
    return s

def strip_comment(line):
    out, in_str, i = '', False, 0
    while i < len(line):
        if line[i] == '’': in_str = not in_str
        if not in_str and line[i:i+2] in ('・・', '//'): break
        out += line[i]; i += 1
    return out

def split_statements(line):
    stmts, buf, in_str = [], '', False
    for ch in line:
        if ch == '’': in_str = not in_str; buf += ch
        elif ch == '。' and not in_str:
            if buf.strip(): stmts.append(buf.strip())
            buf = ''
        else: buf += ch
    if buf.strip(): stmts.append(buf.strip())
    return stmts


def split_ll_items(body, seps='、'):
    # LL入れ子対応の要素分割: 内側LLは」で閉じる。文字列’〜’内は保護
    items, buf, depth, in_str = [], '', 0, False
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == '’': in_str = not in_str
        if not in_str:
            if body[i:i+2].upper() == 'LL' and (i+2 >= len(body) or not body[i+2].isalnum()):
                depth += 1; buf += body[i:i+2]; i += 2; continue
            if ch == '」': depth -= 1; buf += ch; i += 1; continue
            if ch in seps and depth == 0:
                items.append(buf); buf = ''; i += 1; continue
        buf += ch; i += 1
    if buf.strip(): items.append(buf)
    return items

def ll_value(tok):
    # LLで始まる字句 → 入れ子リテラル、その他はdatum
    t = tok.strip()
    m = re.match(r'^LL(?:\s+|(?=[^A-Za-z0-9])|$)(.*?)」?$', t, re.I | re.S)
    if t.upper().startswith('LL'):
        inner = m.group(1)
        if '；' in inner or ';' in inner:
            pairs = []
            for p in split_ll_items(inner):
                if not p.strip(): continue
                k, v = re.split(r'[；;]', p, maxsplit=1)
                pairs.append((datum(k), ll_value(v)))
            return ('dictval', pairs)
        return ('listval', [ll_value(p) for p in split_ll_items(inner) if p.strip()])
    return datum(t)

class UniErr(Exception):
    def __init__(self, key, detail=''):
        self.key, self.detail = key, detail

MSG = {
 'ja': {
   'for_no_range': 'FOR文には「(リスト)から」か「(終値)まで」のどちらかが必要です',
   'for_no_start': 'FOR文の開始値が見つかりません(例: FOR 1 「Iが3まで)',
   'for_no_var':   'FOR文のループ変数「〇〇が」が見つかりません',
   'bad_stmt':     'この文を解釈できません。関数名はひらがな、変数は「で始めてください',
   'header':       '【{line}行目】{msg}\n  → {src}',
 },
 'en': {
   'for_no_range': 'FOR needs either "from (list)" or "to (end value)"',
   'for_no_start': 'FOR start value not found (e.g. FOR from 1 as $I to 3)',
   'for_no_var':   'FOR loop variable not found',
   'bad_stmt':     'Cannot parse this statement. Function names must be plain words; variables start with $',
   'header':       '[line {line}] {msg}\n  -> {src}',
 },
}

CMP = [('より大きい','>'),('より小さい','<'),('以上','>='),('以下','<='),
       ('とおなじ','=='),('と同じ','=='),('とちがう','!='),('と違う','!=')]
OPS = {'足す':'+=','たす':'+=','引く':'-=','ひく':'-=',
       '掛ける':'*=','かける':'*=','割る':'/=','わる':'/='}
ORD = r'(?:つ|個|番)目'

# ================= 式アトム(中立表現) =================
def atom(tok):
    tok = tok.strip()
    m = re.match(rf'^「(\S+?)((?:\s*\d+(?:つ|個|番)目){{2,}})$', tok)
    if m:  # 連鎖番地: 「表 1つ目 2つ目
        idxs = [int(x)-1 for x in re.findall(r'(\d+)(?:つ|個|番)目', m.group(2))]
        return ('idxchain', m.group(1), idxs)
    if tok.startswith('’') and tok.endswith('’'):
        content = tok[1:-1]
        if '「' in content and '」' in content:
            parts = re.split(r'「([^\s」]+?)」', content)
            segs = []
            for i, p in enumerate(parts):
                if p == '': continue
                segs.append(('var', p) if i % 2 else ('txt', p))
            return ('fstr', segs)
        return ('str', content)
    if tok in ('ヌル', 'ﾇﾙ'): return ('null',)
    m = re.match(rf'^「(\S+?)\s*(\d+){ORD}$', tok)
    if m: return ('idx', m.group(1), int(m.group(2))-1)
    m = re.match(r'^「(\S+?)\s+(\S+)$', tok)
    if m: return ('key', m.group(1), datum(m.group(2)))
    if tok.startswith('「'): return ('var', tok[1:])
    if re.fullmatch(r'-?\d+(\.\d+)?', tok): return ('num', tok)
    return ('raw', tok)

def datum(tok):
    a = atom(tok)
    return ('str', a[1]) if a[0] == 'raw' else a

# ================= パーサ(→中立IR) =================
class Parser:
    def __init__(self, lang='ja'):
        self.last_var = None
        self.colls = set()
        self.ir = []   # [(depth, node)]
        self.lang = lang
        self.errors = []

    def put(self, depth, node): self.ir.append((depth, node))

    def _cond(self, body):
        if 'または' in body:
            return ('logic', 'or', [self._cond(p) for p in body.split('または')])
        if 'かつ' in body:
            return ('logic', 'and', [self._cond(p) for p in body.split('かつ')])
        body = body.strip()
        if body.endswith('でない'):
            return ('not', self._cond(body[:-3]))
        for jp, op in CMP:
            if jp in body:
                left = body.split(jp)[0]
                m = re.match(r'(「\S+?|’[^’]*’)?\s*(\S+)\s*$', left)
                l = atom(m.group(1)) if m.group(1) else ('var', self.last_var)
                return ('cmp', l, op, atom(m.group(2)))
        return atom(body)

    def stmt(self, s, depth):
        s = s.strip().rstrip('{').strip()
        if not s or s == '}': return depth, 0

        m = re.match(r'^定義\s+(\S+?)((?:\s+￥「\S+)*)\s*$', s)
        if m:
            self.put(depth, ('def', m.group(1), re.findall(r'￥「(\S+)', m.group(2))))
            return depth, +1

        if re.match(r'^FOR\b', s, re.I) and 'まで' not in s:
            lst  = re.search(r'「([^「\s]+?)\s*から', s)
            if not lst: raise UniErr('for_no_range')
            var  = re.search(r'「([^「\s]+?)が', s)
            step = re.search(r'(\d+)ずつ', s)
            v = var.group(1) if var else 'それ'
            self.put(depth, ('foreach', v, lst.group(1), int(step.group(1)) if step else 1))
            self.last_var = v
            return depth, +1

        if re.match(r'^FOR\b', s, re.I):
            var  = re.search(r'「([^「\s]+?)が', s)
            s_end = re.sub(r'「[^「\s]+?が', '', s)
            end  = re.search(rf'(「[^「\s]+?|\d+)まで', s_end)
            step = re.search(r'(\d+)ずつ', s)
            down = 'へる' in s
            if not var: raise UniErr('for_no_var')
            rest = re.sub(rf'「[^「\s]+?が|(「[^「\s]+?|\d+)まで|\d+ずつ(ふえる|へる)?|ふえる|へる|^FOR', '', s, flags=re.I)
            start = re.search(r'\d+', rest)
            if not start: raise UniErr('for_no_start')
            self.put(depth, ('forrange', var.group(1), start.group(0),
                             atom(end.group(1)), step.group(1) if step else '1', down))
            return depth, +1

        if re.fullmatch(r'BREAK', s, re.I):
            self.put(depth, ('break',)); return depth, 0
        if re.fullmatch(r'CONTINUE', s, re.I):
            self.put(depth, ('continue',)); return depth, 0
        if re.fullmatch(r'TRY', s, re.I):
            self.put(depth, ('try',)); return depth, +1
        if re.fullmatch(r'CATCH', s, re.I):
            self.put(depth, ('catch',)); return depth, +1

        if re.match(r'^ELSE\s+IF\b', s, re.I):
            self.put(depth, ('elif', self._cond(re.sub(r'^ELSE\s+IF\s*', '', s, flags=re.I))))
            return depth, +1
        if re.match(r'^ELSE\b', s, re.I):
            self.put(depth, ('else',)); return depth, +1
        if re.match(r'^WHILE\b', s, re.I):
            self.put(depth, ('while', self._cond(re.sub(r'^WHILE\s*', '', s, flags=re.I))))
            return depth, +1
        if re.match(r'^IF\b', s, re.I):
            self.put(depth, ('if', self._cond(re.sub(r'^IF\s*', '', s, flags=re.I))))
            return depth, +1

        m = re.match(r'^「(\S+?)\s*=\s*(.+)$', s)
        if m:
            name, rhs = m.group(1), m.group(2).strip()
            mex = re.match(r'^EX\s*’([^’]+)’(?:\s*、(.*))?$', rhs, re.I)
            if mex:
                args = [atom(p) for p in mex.group(2).split('、')] if mex.group(2) else []
                self.put(depth, ('assignext', name, mex.group(1), args))
                self.last_var = name
                return depth, 0
            mll = re.match(r'^LL(?:\s+|(?=[^A-Za-z0-9])|$)(.*)$', rhs, re.I | re.S)
            if mll and ('；' in mll.group(1) or ';' in mll.group(1)):
                pairs = []
                for p in split_ll_items(mll.group(1)):
                    if not p.strip(): continue
                    k, v = re.split(r'[；;]', p, maxsplit=1)
                    pairs.append((datum(k), ll_value(v)))
                self.put(depth, ('dictlit', name, pairs)); self.colls.add(name)
            elif mll:
                items = [ll_value(p) for p in split_ll_items(mll.group(1)) if p.strip()]
                self.put(depth, ('listlit', name, items)); self.colls.add(name)
            else:
                parts = [p.strip() for p in rhs.split('、')]
                if len(parts) > 1:
                    self.put(depth, ('assigncall', name, parts[0], [atom(p) for p in parts[1:]]))
                elif re.fullmatch(r'[ぁ-ゖー]+', rhs):
                    self.put(depth, ('assigncall', name, rhs, []))
                else:
                    self.put(depth, ('assign', name, atom(rhs)))
            self.last_var = name
            return depth, 0

        m = re.match(rf'^「(\S+?)\s+(\S+)\s*から$', s)
        if m:
            self.put(depth, ('assign', m.group(1), atom(m.group(2))))
            self.last_var = m.group(1); return depth, 0
        m = re.match(r'^「(\S+?)(から)?$', s)
        if m and not any(v in s for v in ('足す','渡す','出す','消す','かえる')):
            self.put(depth, ('assign', m.group(1), ('num','0')))
            self.last_var = m.group(1); return depth, 0

        m = re.match(rf'^「(\S+?)\s+(\d+){ORD}\s+(\S+)\s+かえる$', s)
        if m:
            self.put(depth, ('setidx', m.group(1), int(m.group(2))-1, datum(m.group(3)))); return depth, 0
        m = re.match(rf'^「(\S+?)\s+(\S+?)\s+(?:(\d+){ORD}\s+)?(\S+)\s+かえる$', s)
        if m:
            self.put(depth, ('setkey', m.group(1), datum(m.group(2)), datum(m.group(4)))); return depth, 0

        m = re.match(rf'^「(\S+?)\s+(\d+){ORD}\s+消す\s+(左|ヌル)$', s)
        if m:
            kind = 'delshift' if m.group(3) == '左' else 'delnull'
            self.put(depth, (kind, m.group(1), int(m.group(2))-1)); return depth, 0

        s2 = re.sub(r'^「(\S+?)に\s*', r'「\1 ', s)   # 明示対象: 「Xに → 「X (案B採用)
        m = re.match(r'^(「\S+\s+)?(\S+?)\s*(ずつ)?(足す|たす|引く|ひく|掛ける|かける|割る|わる)$', s2)
        if m:
            target = m.group(1).strip()[1:] if m.group(1) else self.last_var
            if target in self.colls and m.group(4) in ('足す','たす'):
                self.put(depth, ('append', target, datum(m.group(2))))
            else:
                self.put(depth, ('aug', target, OPS[m.group(4)], atom(m.group(2))))
            return depth, 0

        m = re.match(r'^(最後に)?\s*「?(\S+?)\s*渡す$', s)
        if m:
            self.put(depth, ('return', ('var', m.group(2)))); return depth, 0

        m = re.match(r'^(.+?)\s*出す$', s)
        if m:
            self.put(depth, ('print', atom(m.group(1)))); return depth, 0

        mex = re.match(r'^EX\s*’([^’]+)’(?:\s*、(.*))?$', s, re.I)
        if mex:
            args = [atom(p) for p in mex.group(2).split('、')] if mex.group(2) else []
            self.put(depth, ('externcall', mex.group(1), args))
            return depth, 0
        parts = [p.strip() for p in s.split('、')]
        if not re.fullmatch(r'[ぁ-ゖー]+', parts[0]):
            raise UniErr('bad_stmt')
        self.put(depth, ('call', parts[0], [atom(p) for p in parts[1:]]))
        return depth, 0

    def expand_use(self, src):
        out = []
        for line in src.split('\n'):
            m = re.match(r'^\s*USE\s*’([^’]+)’\s*。?\s*$', line, re.I)
            if m:
                try:
                    out.append(self.expand_use(open(m.group(1), encoding='utf-8').read()))
                except FileNotFoundError:
                    out.append(line)  # エラーは後段で
            else:
                out.append(line)
        return '\n'.join(out)

    def parse(self, src):
        src = normalize(self.expand_use(src))
        indents, depth, pending = [0], 0, 0
        for lineno, raw in enumerate(src.split('\n'), 1):
            if not strip_comment(raw).strip(): continue
            ind = len(raw) - len(raw.lstrip('　 \t'))
            if pending:
                indents.append(ind); depth += pending; pending = 0
            else:
                while len(indents) > 1 and ind < indents[-1]:
                    indents.pop(); depth -= 1
            for st in split_statements(strip_comment(raw.strip())):
                try:
                    depth, opened = self.stmt(st, depth)
                    pending += opened
                except UniErr as e:
                    T = MSG[self.lang]
                    self.errors.append(T['header'].format(
                        line=lineno, msg=T[e.key], src=st))
                except Exception:
                    T = MSG[self.lang]
                    self.errors.append(T['header'].format(
                        line=lineno, msg=T['bad_stmt'], src=st))
        return self.ir, self.colls

# ================= バックエンド: Python =================
class PyBackend:
    name = 'python'
    BUILTIN = {'ながさ': ('len({a})', None), 'へいほうこん': ('math.sqrt({a})', 'math'),
               'きく': ('input()', None), 'あまり': ('({a0} % {a1})', None)}
    def __init__(self, colls):
        self.colls = colls
        self.imports = set()
    def fcall(self, fn, args):
        rendered = [self.e(x) for x in args]
        a = ', '.join(rendered)
        if fn in self.BUILTIN:
            tpl, mod = self.BUILTIN[fn]
            if mod: self.imports.add(mod)
            if '{a0}' in tpl:
                for i, r in enumerate(rendered): tpl = tpl.replace('{a%d}' % i, r)
                return tpl
            return tpl.format(a=a)
        return f'{fn}({a})'
    def ext(self, code, args):
        if '.' in code: self.imports.add(code.split('.')[0])
        return f'{code}({", ".join(self.e(x) for x in args)})'
    def e(self, a):
        k = a[0]
        if k == 'str':  return '"' + a[1].replace('"','\\"') + '"'
        if k == 'fstr':
            body = ''.join(p[1] if p[0]=='txt' else '{'+p[1]+'}' for p in a[1])
            return 'f"' + body + '"'
        if k == 'num':  return a[1]
        if k == 'null': return 'None'
        if k == 'var':  return a[1]
        if k == 'idx':  return f'{a[1]}[{a[2]}]'
        if k == 'idxchain': return a[1] + ''.join(f'[{i}]' for i in a[2])
        if k == 'key':  return f'{a[1]}[{self.e(a[2])}]'
        if k == 'listval': return '[' + ', '.join(self.e(x) for x in a[1]) + ']'
        if k == 'dictval': return '{' + ', '.join(f'{self.e(kk)}: {self.e(vv)}' for kk, vv in a[1]) + '}'
        if k == 'cmp':  return f'{self.e(a[1])} {a[2]} {self.e(a[3])}'
        if k == 'logic': return (' ' + ('or' if a[1]=='or' else 'and') + ' ').join(f'({self.e(x)})' for x in a[2])
        if k == 'not':  return f'not ({self.e(a[1])})'
        if k == 'raw':  return a[1]
    def render(self, ir):
        out = []
        for depth, n in ir:
            pad, k = '    '*depth, n[0]
            if k=='def':       out.append(f'{pad}def {n[1]}({", ".join(n[2])}):')
            elif k=='forrange':
                v,a,b,c,down = n[1],n[2],self.e(n[3]),n[4],n[5]
                rng = f'range({a}, {b}-1, -{c})' if down else f'range({a}, {b}+1, {c})'
                out.append(f'{pad}for {v} in {rng}:')
            elif k=='foreach':
                seq = n[2] + (f'[::{n[3]}]' if n[3] != 1 else '')
                out.append(f'{pad}for {n[1]} in {seq}:')
            elif k=='if':      out.append(f'{pad}if {self.e(n[1])}:')
            elif k=='elif':    out.append(f'{pad}elif {self.e(n[1])}:')
            elif k=='else':    out.append(f'{pad}else:')
            elif k=='while':   out.append(f'{pad}while {self.e(n[1])}:')
            elif k=='assign':  out.append(f'{pad}{n[1]} = {self.e(n[2])}')
            elif k=='assigncall': out.append(f'{pad}{n[1]} = {self.fcall(n[2], n[3])}')
            elif k=='assignext': out.append(f'{pad}{n[1]} = {self.ext(n[2], n[3])}')
            elif k=='externcall': out.append(f'{pad}{self.ext(n[1], n[2])}')
            elif k=='listlit': out.append(f'{pad}{n[1]} = [{", ".join(self.e(a) for a in n[2])}]')
            elif k=='dictlit': out.append(f'{pad}{n[1]} = {{{", ".join(f"{self.e(kk)}: {self.e(vv)}" for kk,vv in n[2])}}}')
            elif k=='setidx':  out.append(f'{pad}{n[1]}[{n[2]}] = {self.e(n[3])}')
            elif k=='setkey':  out.append(f'{pad}{n[1]}[{self.e(n[2])}] = {self.e(n[3])}')
            elif k=='delshift':out.append(f'{pad}del {n[1]}[{n[2]}]')
            elif k=='delnull': out.append(f'{pad}{n[1]}[{n[2]}] = None')
            elif k=='append':  out.append(f'{pad}{n[1]}.append({self.e(n[2])})')
            elif k=='aug':     out.append(f'{pad}{n[1]} {n[2]} {self.e(n[3])}')
            elif k=='return':  out.append(f'{pad}return {self.e(n[1])}')
            elif k=='print':   out.append(f'{pad}print({self.e(n[1])})')
            elif k=='call':    out.append(f'{pad}{self.fcall(n[1], n[2])}')
            elif k=='break':   out.append(f'{pad}break')
            elif k=='continue':out.append(f'{pad}continue')
            elif k=='try':     out.append(f'{pad}try:')
            elif k=='catch':   out.append(f'{pad}except Exception as ex:')
        head = [f'import {m}' for m in sorted(self.imports)]
        return '\n'.join(head + out)

# ================= バックエンド: PHP =================
class PhpBackend:
    name = 'php'
    BUILTIN = {'ながさ': 'count({a})', 'へいほうこん': 'sqrt({a})', 'きく': 'trim(fgets(STDIN))', 'あまり': '({a0} % {a1})'}
    def __init__(self, colls): self.colls = colls
    def fcall(self, fn, args):
        a = ', '.join(self.e(x) for x in args)
        if fn in self.BUILTIN:
            tpl = self.BUILTIN[fn]
            if '{a0}' in tpl:
                parts = a.split(', ')
                for i, r in enumerate(parts): tpl = tpl.replace('{a%d}' % i, r)
                return tpl
            return tpl.format(a=a)
        return f'{fn}({a})'
    def e(self, a):
        k = a[0]
        if k == 'str':  return '"' + a[1].replace('"','\\"') + '"'
        if k == 'fstr':
            body = ''.join(p[1] if p[0]=='txt' else '{$'+p[1]+'}' for p in a[1])
            return '"' + body + '"'
        if k == 'num':  return a[1]
        if k == 'null': return 'null'
        if k == 'var':  return '$' + a[1]
        if k == 'idx':  return f'${a[1]}[{a[2]}]'
        if k == 'idxchain': return '$' + a[1] + ''.join(f'[{i}]' for i in a[2])
        if k == 'key':  return f'${a[1]}[{self.e(a[2])}]'
        if k == 'listval': return '[' + ', '.join(self.e(x) for x in a[1]) + ']'
        if k == 'dictval': return '[' + ', '.join(f'{self.e(kk)} => {self.e(vv)}' for kk, vv in a[1]) + ']'
        if k == 'cmp':  return f'{self.e(a[1])} {a[2]} {self.e(a[3])}'
        if k == 'logic': return (' ' + ('||' if a[1]=='or' else '&&') + ' ').join(f'({self.e(x)})' for x in a[2])
        if k == 'not':  return f'!({self.e(a[1])})'
        if k == 'raw':  return a[1]
    def pr(self, a):  # print式: コレクションはjson化(実行時判定込み)
        ex = self.e(a)
        if a[0] == 'var' and a[1] in self.colls:
            return f'json_encode({ex}, JSON_UNESCAPED_UNICODE)'
        if a[0] in ('var', 'key', 'idx', 'idxchain'):
            return f'(is_array({ex}) ? json_encode({ex}, JSON_UNESCAPED_UNICODE) : {ex})'
        return ex
    def render(self, ir):
        out, stack = ['<?php'], []   # stack: 開いたブロックのdepth
        def close_to(d):
            while stack and stack[-1] >= d:
                sd = stack.pop(); out.append('    '*sd + '}')
        for depth, n in ir:
            close_to(depth)
            pad, k = '    '*depth, n[0]
            opens = k in ('def','forrange','foreach','if','elif','else','while')
            if k=='def':
                out.append(f'{pad}function {n[1]}({", ".join("$"+p for p in n[2])}) {{')
            elif k=='forrange':
                v,a,b,c,down = '$'+n[1], n[2], self.e(n[3]), n[4], n[5]
                if down: out.append(f'{pad}for ({v} = {a}; {v} >= {b}; {v} -= {c}) {{')
                else:    out.append(f'{pad}for ({v} = {a}; {v} <= {b}; {v} += {c}) {{')
            elif k=='foreach':
                v, seq, st = '$'+n[1], '$'+n[2], n[3]
                if st == 1:
                    out.append(f'{pad}foreach ({seq} as {v}) {{')
                else:
                    i = f'${n[1]}_i'
                    out.append(f'{pad}for ({i} = 0; {i} < count({seq}); {i} += {st}) {{')
                    out.append(f'{pad}    {v} = {seq}[{i}];')
            elif k=='if':      out.append(f'{pad}if ({self.e(n[1])}) {{')
            elif k=='elif':
                if out and out[-1].strip() == '}' and stack is not None: pass
                # elifは直前ブロックを閉じてelseif
                out.append(f'{pad}elseif ({self.e(n[1])}) {{')
            elif k=='else':    out.append(f'{pad}else {{')
            elif k=='while':   out.append(f'{pad}while ({self.e(n[1])}) {{')
            elif k=='assign':  out.append(f'{pad}${n[1]} = {self.e(n[2])};')
            elif k=='assigncall': out.append(f'{pad}${n[1]} = {self.fcall(n[2], n[3])};')
            elif k=='assignext': out.append(f'{pad}${n[1]} = {n[2]}({", ".join(self.e(a) for a in n[3])});')
            elif k=='externcall': out.append(f'{pad}{n[1]}({", ".join(self.e(a) for a in n[2])});')
            elif k=='listlit': out.append(f'{pad}${n[1]} = [{", ".join(self.e(a) for a in n[2])}];')
            elif k=='dictlit': out.append(f'{pad}${n[1]} = [{", ".join(f"{self.e(kk)} => {self.e(vv)}" for kk,vv in n[2])}];')
            elif k=='setidx':  out.append(f'{pad}${n[1]}[{n[2]}] = {self.e(n[3])};')
            elif k=='setkey':  out.append(f'{pad}${n[1]}[{self.e(n[2])}] = {self.e(n[3])};')
            elif k=='delshift':out.append(f'{pad}array_splice(${n[1]}, {n[2]}, 1);')
            elif k=='delnull': out.append(f'{pad}${n[1]}[{n[2]}] = null;')
            elif k=='append':  out.append(f'{pad}${n[1]}[] = {self.e(n[2])};')
            elif k=='aug':     out.append(f'{pad}${n[1]} {n[2]} {self.e(n[3])};')
            elif k=='return':  out.append(f'{pad}return {self.e(n[1])};')
            elif k=='print':   out.append(f'{pad}echo {self.pr(n[1])}, PHP_EOL;')
            elif k=='call':    out.append(f'{pad}{self.fcall(n[1], n[2])};')
            elif k=='break':   out.append(f'{pad}break;')
            elif k=='continue':out.append(f'{pad}continue;')
            elif k=='try':     out.append(f'{pad}try {{'); opens=True
            elif k=='catch':   out.append(f'{pad}catch (Exception $ex) {{'); opens=True
            if opens: stack.append(depth)
        close_to(0)
        return '\n'.join(out)

# elif直前のブロック閉じ調整: close_toがelifでも閉じるため、elseif連結のには閉じた } を残したままでよい(PHPは } elseif { 形式でなくても if(){...} elseif(){...} は不可。要修正)
# → renderで対応済みとするため、後段で } の直後の elseif/else を } elseif に結合する
def php_join_else(code):
    code = re.sub(r'\}\n(\s*)elseif', r'} elseif', code)
    code = re.sub(r'\}\n(\s*)else \{', r'} else {', code)
    code = re.sub(r'\}\n(\s*)catch', r'} catch', code)
    return code


# ================= バックエンド: JavaScript =================
class JsBackend:
    name = 'js'
    BUILTIN = {'ながさ': '({a}).length', 'へいほうこん': 'Math.sqrt({a})', 'きく': "require('fs').readFileSync(0,'utf8').trim()", 'あまり': '({a0} % {a1})'}
    def __init__(self, colls): self.colls = colls
    def fcall(self, fn, args):
        rendered = [self.e(x) for x in args]
        a = ', '.join(rendered)
        if fn in self.BUILTIN:
            tpl = self.BUILTIN[fn]
            if '{a0}' in tpl:
                for i, r in enumerate(rendered): tpl = tpl.replace('{a%d}' % i, r)
                return tpl
            return tpl.format(a=a)
        return f'{fn}({a})'
    def e(self, a):
        k = a[0]
        if k == 'str':  return '"' + a[1].replace('"','\\"') + '"'
        if k == 'fstr':
            body = ''.join(p[1] if p[0]=='txt' else '${'+p[1]+'}' for p in a[1])
            return '`' + body + '`'
        if k == 'num':  return a[1]
        if k == 'null': return 'null'
        if k == 'var':  return a[1]
        if k == 'idx':  return f'{a[1]}[{a[2]}]'
        if k == 'idxchain': return a[1] + ''.join(f'[{i}]' for i in a[2])
        if k == 'key':  return f'{a[1]}[{self.e(a[2])}]'
        if k == 'listval': return '[' + ', '.join(self.e(x) for x in a[1]) + ']'
        if k == 'dictval': return '{' + ', '.join(f'{self.e(kk)}: {self.e(vv)}' for kk, vv in a[1]) + '}'
        if k == 'cmp':  return f'{self.e(a[1])} {a[2]} {self.e(a[3])}'
        if k == 'logic': return (' ' + ('||' if a[1]=='or' else '&&') + ' ').join(f'({self.e(x)})' for x in a[2])
        if k == 'not':  return f'!({self.e(a[1])})'
        if k == 'raw':  return a[1]
    def pr(self, a):
        if a[0] == 'var' and a[1] in self.colls:
            return f'JSON.stringify({self.e(a)})'
        return self.e(a)
    def render(self, ir):
        out, stack, declared = [], [], set()
        def close_to(d):
            while stack and stack[-1] >= d:
                out.append('    '*stack.pop() + '}')
        def decl(name):
            if name in declared: return ''
            declared.add(name); return 'let '
        for depth, n in ir:
            close_to(depth)
            pad, k = '    '*depth, n[0]
            opens = k in ('def','forrange','foreach','if','elif','else','while')
            if k=='def':
                declared = set(n[2])
                out.append(f'{pad}function {n[1]}({", ".join(n[2])}) {{')
            elif k=='forrange':
                v,a,b,c,down = n[1], n[2], self.e(n[3]), n[4], n[5]
                declared.add(v)
                if down: out.append(f'{pad}for (let {v} = {a}; {v} >= {b}; {v} -= {c}) {{')
                else:    out.append(f'{pad}for (let {v} = {a}; {v} <= {b}; {v} += {c}) {{')
            elif k=='foreach':
                v, seq, st = n[1], n[2], n[3]
                declared.add(v)
                if st == 1: out.append(f'{pad}for (const {v} of {seq}) {{')
                else:
                    i = f'{n[1]}_i'
                    out.append(f'{pad}for (let {i} = 0; {i} < {seq}.length; {i} += {st}) {{')
                    out.append(f'{pad}    const {v} = {seq}[{i}];')
            elif k=='if':      out.append(f'{pad}if ({self.e(n[1])}) {{')
            elif k=='elif':    out.append(f'{pad}elif_MARK ({self.e(n[1])}) {{')
            elif k=='else':    out.append(f'{pad}else {{')
            elif k=='while':   out.append(f'{pad}while ({self.e(n[1])}) {{')
            elif k=='assign':  out.append(f'{pad}{decl(n[1])}{n[1]} = {self.e(n[2])};')
            elif k=='assigncall': out.append(f'{pad}{decl(n[1])}{n[1]} = {self.fcall(n[2], n[3])};')
            elif k=='assignext': out.append(f'{pad}{decl(n[1])}{n[1]} = {n[2]}({", ".join(self.e(a) for a in n[3])});')
            elif k=='externcall': out.append(f'{pad}{n[1]}({", ".join(self.e(a) for a in n[2])});')
            elif k=='listlit': out.append(f'{pad}{decl(n[1])}{n[1]} = [{", ".join(self.e(a) for a in n[2])}];')
            elif k=='dictlit': out.append(f'{pad}{decl(n[1])}{n[1]} = {{{", ".join(f"{self.e(kk)}: {self.e(vv)}" for kk,vv in n[2])}}};')
            elif k=='setidx':  out.append(f'{pad}{n[1]}[{n[2]}] = {self.e(n[3])};')
            elif k=='setkey':  out.append(f'{pad}{n[1]}[{self.e(n[2])}] = {self.e(n[3])};')
            elif k=='delshift':out.append(f'{pad}{n[1]}.splice({n[2]}, 1);')
            elif k=='delnull': out.append(f'{pad}{n[1]}[{n[2]}] = null;')
            elif k=='append':  out.append(f'{pad}{n[1]}.push({self.e(n[2])});')
            elif k=='aug':     out.append(f'{pad}{n[1]} {n[2]} {self.e(n[3])};')
            elif k=='return':  out.append(f'{pad}return {self.e(n[1])};')
            elif k=='print':   out.append(f'{pad}console.log({self.pr(n[1])});')
            elif k=='call':    out.append(f'{pad}{self.fcall(n[1], n[2])};')
            elif k=='break':   out.append(f'{pad}break;')
            elif k=='continue':out.append(f'{pad}continue;')
            elif k=='try':     out.append(f'{pad}try {{'); opens=True
            elif k=='catch':   out.append(f'{pad}catch (ex) {{'); opens=True
            if opens: stack.append(depth)
        close_to(0)
        code = '\n'.join(out)
        code = re.sub(r'\}\n(\s*)elif_MARK', r'} else if', code)
        code = re.sub(r'\}\n(\s*)else \{', r'} else {', code)
        code = re.sub(r'\}\n(\s*)catch', r'} catch', code)
        return code

# ================= バックエンド: Java(型推論つき) =================
class JavaBackend:
    name = 'java'
    BUILTIN = {'ながさ': ('{a}.size()', 'int'), 'へいほうこん': ('Math.sqrt({a})', 'double'), 'きく': ('SC.nextLine()', 'String'), 'あまり': ('({a0} % {a1})', 'int')}
    def __init__(self, colls):
        self.colls = colls
        self.fnparams = {}
        self.scopes = {}
    def cast_arg(self, x, t, ptype):
        ex = self.e(x, t)
        if x[0] in ('var','idx','key'):
            xt = t.get(x[1], 'Object') if x[0]=='var' else 'Object'
            if xt == 'Object' and ptype == 'int':    return f'((Number){ex}).intValue()'
            if xt == 'Object' and ptype == 'double': return f'((Number){ex}).doubleValue()'
        return ex
    def fcall(self, fn, args, t):
        if fn in self.BUILTIN:
            rendered = [self.cast_arg(x, t, 'int') if '{a0}' in self.BUILTIN[fn][0] else self.e(x, t) for x in args]
            tpl = self.BUILTIN[fn][0]
            if '{a0}' in tpl:
                for i, r in enumerate(rendered): tpl = tpl.replace('{a%d}' % i, r)
                return tpl
            return tpl.format(a=', '.join(rendered))
        ptypes = [self.scopes.get(fn, {}).get(p, 'Object') for p in self.fnparams.get(fn, [])]
        rendered = [self.cast_arg(x, t, ptypes[i] if i < len(ptypes) else 'Object')
                    for i, x in enumerate(args)]
        return f'{fn}({", ".join(rendered)})'
    # --- 型推論: スコープ毎に 変数→型 を2パスで確定 ---
    def infer(self, ir):
        scopes = {'<main>': {}}
        fn_ret = {}
        cur = '<main>'
        for depth, n in ir:
            k = n[0]
            if k == 'def':
                cur = n[1]; scopes[cur] = {p: 'int' for p in n[2]}
                self.fnparams[cur] = list(n[2])
                continue
            if depth == 0: cur = '<main>'
            t = scopes[cur]
            if k=='assign':
                a = n[2]
                if a[0]=='num': t[n[1]] = 'double' if '.' in a[1] else 'int'
                elif a[0] in ('str','fstr'): t[n[1]] = 'String'
                elif a[0]=='var': t[n[1]] = t.get(a[1], 'Object')
                else: t[n[1]] = 'Object'
            elif k=='listlit': t[n[1]] = 'List<Object>'
            elif k=='dictlit': t[n[1]] = 'Map<Object,Object>'
            elif k=='assigncall':
                t[n[1]] = self.BUILTIN[n[2]][1] if n[2] in self.BUILTIN else '@ret:' + n[2]
            elif k=='assignext': t[n[1]] = 'double'
            elif k=='aug':
                if n[2]=='/=' or (n[3][0]=='num' and '.' in n[3][1]) or \
                   (n[3][0]=='var' and t.get(n[3][1])=='Object'):
                    t[n[1]] = 'double'
            elif k=='forrange': t[n[1]] = 'int'
            elif k=='foreach':
                t[n[1]] = 'Object'
                if t.get(n[2]) == 'int': t[n[2]] = 'List<Object>'   # 反復対象の引数はリスト
            elif k=='return':
                fn_ret[cur] = t.get(n[1][1], 'Object')
        for sc in scopes.values():
            for v, ty in sc.items():
                if isinstance(ty, str) and ty.startswith('@ret:'):
                    sc[v] = fn_ret.get(ty[5:], 'Object')
        return scopes, fn_ret
    def e(self, a, t):
        k = a[0]
        if k == 'str':  return '"' + a[1].replace('"','\\"') + '"'
        if k == 'fstr':
            segs = []
            for p in a[1]:
                segs.append('"' + p[1].replace('"','\\"') + '"' if p[0]=='txt' else p[1])
            return ' + '.join(segs)
        if k == 'num':  return a[1]
        if k == 'null': return 'null'
        if k == 'var':  return a[1]
        if k == 'idx':  return f'{a[1]}.get({a[2]})'
        if k == 'idxchain':
            expr = a[1]
            for i in a[2][:-1]: expr = f'((List<Object>){expr}.get({i}))'
            return f'{expr}.get({a[2][-1]})'
        if k == 'key':  return f'{a[1]}.get({self.e(a[2], t)})'
        if k == 'listval': return 'new ArrayList<>(Arrays.asList(' + ', '.join(self.e(x, t) for x in a[1]) + '))'
        if k == 'dictval':
            return 'new LinkedHashMap<>(Map.of(' + ', '.join(f'{self.e(kk, t)}, {self.e(vv, t)}' for kk, vv in a[1]) + '))'
        if k == 'cmp':
            l = self.e(a[1], t)
            if a[1][0]=='var' and t.get(a[1][1]) == 'Object':
                l = f'((Number){l}).doubleValue()'
            return f'{l} {a[2]} {self.e(a[3], t)}'
        if k == 'logic': return (' ' + ('||' if a[1]=='or' else '&&') + ' ').join(f'({self.e(x, t)})' for x in a[2])
        if k == 'not':  return f'!({self.e(a[1], t)})'
        if k == 'raw':  return a[1]
    def render(self, ir):
        scopes, fn_ret = self.infer(ir)
        self.scopes = scopes
        funcs, main = [], []
        cur, buf, t = '<main>', None, scopes['<main>']
        declared = set()
        stack = []
        def sink(): return buf if buf is not None else main
        def close_to(d, base):
            while stack and stack[-1] >= d:
                sink().append('    '*(stack.pop()+base) + '}')
        for depth, n in ir:
            k = n[0]
            if k == 'def':
                close_to(0, 2 if buf is not None else 2)
                if buf: funcs.append(buf)
                cur = n[1]; t = scopes[cur]; declared = set(n[2]); buf = []
                ret = fn_ret.get(cur, 'void')
                params = ', '.join(f'{t[p]} {p}' for p in n[2])
                buf.append(f'    static {ret} {cur}({params}) {{')
                stack.append(0)
                continue
            if depth == 0 and buf is not None and k != 'def':
                close_to(0, 2)
                funcs.append(buf); buf = None
                cur, t, declared = '<main>', scopes['<main>'], set()
            base = 2
            close_to(depth, base)
            pad = '    '*(depth+base)
            o = sink()
            opens = k in ('forrange','foreach','if','elif','else','while')
            def decl(name):
                if name in declared: return ''
                declared.add(name)
                ty = t.get(name, 'Object')
                return ty + ' '
            if k=='forrange':
                v,a,b,c,down = n[1], n[2], self.e(n[3], t), n[4], n[5]
                declared.add(v)
                if down: o.append(f'{pad}for (int {v} = {a}; {v} >= {b}; {v} -= {c}) {{')
                else:    o.append(f'{pad}for (int {v} = {a}; {v} <= {b}; {v} += {c}) {{')
            elif k=='foreach':
                v, seq, st = n[1], n[2], n[3]
                declared.add(v)
                if st == 1: o.append(f'{pad}for (Object {v} : {seq}) {{')
                else:
                    i = f'{v}_i'
                    o.append(f'{pad}for (int {i} = 0; {i} < {seq}.size(); {i} += {st}) {{')
                    o.append(f'{pad}    Object {v} = {seq}.get({i});')
            elif k=='if':      o.append(f'{pad}if ({self.e(n[1], t)}) {{')
            elif k=='elif':    o.append(f'{pad}elif_MARK ({self.e(n[1], t)}) {{')
            elif k=='else':    o.append(f'{pad}else {{')
            elif k=='while':   o.append(f'{pad}while ({self.e(n[1], t)}) {{')
            elif k=='assign':  o.append(f'{pad}{decl(n[1])}{n[1]} = {self.e(n[2], t)};')
            elif k=='assigncall': o.append(f'{pad}{decl(n[1])}{n[1]} = {self.fcall(n[2], n[3], t)};')
            elif k=='assignext': o.append(f'{pad}{decl(n[1])}{n[1]} = {n[2]}({", ".join(self.e(a, t) for a in n[3])});')
            elif k=='externcall': o.append(f'{pad}{n[1]}({", ".join(self.e(a, t) for a in n[2])});')
            elif k=='listlit':
                items = ', '.join(self.e(a, t) for a in n[2])
                o.append(f'{pad}{decl(n[1])}{n[1]} = new ArrayList<>(Arrays.asList({items}));' if items
                         else f'{pad}{decl(n[1])}{n[1]} = new ArrayList<>();')
            elif k=='dictlit':
                o.append(f'{pad}{decl(n[1])}{n[1]} = new LinkedHashMap<>();')
                for kk, vv in n[2]:
                    o.append(f'{pad}{n[1]}.put({self.e(kk, t)}, {self.e(vv, t)});')
            elif k=='setidx':  o.append(f'{pad}{n[1]}.set({n[2]}, {self.e(n[3], t)});')
            elif k=='setkey':  o.append(f'{pad}{n[1]}.put({self.e(n[2], t)}, {self.e(n[3], t)});')
            elif k=='delshift':o.append(f'{pad}{n[1]}.remove({n[2]});')
            elif k=='delnull': o.append(f'{pad}{n[1]}.set({n[2]}, null);')
            elif k=='append':  o.append(f'{pad}{n[1]}.add({self.e(n[2], t)});')
            elif k=='aug':
                srcv = self.e(n[3], t)
                if n[3][0]=='var' and t.get(n[3][1])=='Object':
                    srcv = f'((Number){srcv}).doubleValue()'
                o.append(f'{pad}{n[1]} {n[2]} {srcv};')
            elif k=='return':  o.append(f'{pad}return {self.e(n[1], t)};')
            elif k=='print':
                v = self.e(n[1], t)
                o.append(f'{pad}System.out.println({v});')
            elif k=='call':    o.append(f'{pad}{self.fcall(n[1], n[2], t)};')
            elif k=='break':   o.append(f'{pad}break;')
            elif k=='continue':o.append(f'{pad}continue;')
            elif k=='try':     o.append(f'{pad}try {{'); opens=True
            elif k=='catch':   o.append(f'{pad}catch (Exception ex) {{'); opens=True
            if opens: stack.append(depth)
        close_to(0, 2)
        if buf: funcs.append(buf); buf = None
        body = []
        body.append('import java.util.*;')
        body.append('public class Main {')
        body.append('    static Scanner SC = new Scanner(System.in);')
        for f in funcs: body.extend(f)
        body.append('    public static void main(String[] args) {')
        body.extend('    ' + l if l.strip() else l for l in main)
        body.append('    }')
        body.append('}')
        code = '\n'.join(body)
        code = re.sub(r'\}\n(\s*)elif_MARK', r'} else if', code)
        code = re.sub(r'\}\n(\s*)else \{', r'} else {', code)
        return code



# ================= 識別子の英名変換(--names=romaji|en) =================
NAME_DICT = {
 'りんご':'apple','みかん':'orange','ばなな':'banana','ぶどう':'grape','もも':'peach','すいか':'watermelon',
 '数':'count','かず':'count','こすう':'count','合計':'total','答え':'answer','上限':'limit',
 'ざんだか':'balance','残高':'balance','くだもの':'fruit','きかい':'machine','じしょ':'dict',
 'てん':'score','ね':'root','いま':'now','なか':'value','めも':'memo','実':'item','それ':'it',
 'から箱':'emptyBox','かず表':'countTable','ねだん':'price','りんごの数':'appleCount',
 'たす':'add','足す':'add','ひく':'sub','引く':'sub','ごうけいする':'sum','する':'do',
 'ながさ':'ながさ','へいほうこん':'へいほうこん',  # 組み込みは変換しない
}
PARTICLES = ('の','を','が','に','は')
RESERVED = {
 'py':  {'sum','list','dict','print','len','max','min','range','set','str','int','id','type','input','next','it'},
 'php': {'list','print','echo','array','count','empty','isset','unset','function','class'},
 'js':  {'let','const','var','function','class','new','this','delete','in','of','it'},
 'java':{'int','double','float','long','short','byte','char','boolean','class','new','this','sum'},
}

class NameMapper:
    def __init__(self, mode, target):
        self.mode, self.target = mode, target
        self.map, self.used = {}, set()
        try:
            import pykakasi
            self.kks = pykakasi.kakasi()
        except Exception:
            self.kks = None
    def romaji(self, w):
        if self.kks:
            return ''.join(i['hepburn'] for i in self.kks.convert(w)) or w
        return w
    def words(self, name):
        # 助詞で分割: りんごの数→[りんご,数] / りんごをたす→[たす,りんご](動詞先行に反転)
        if 'を' in name:
            obj, verb = name.split('を', 1)
            return [verb, obj]
        parts = re.split('|'.join(PARTICLES), name)
        return [p for p in parts if p]
    def eng(self, w):
        if w in NAME_DICT: return NAME_DICT[w]
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', w): return w
        return self.romaji(w)
    def case(self, words):
        words = [w for w in words if w]
        if self.target == 'py':
            return '_'.join(w.lower() for w in words)
        return words[0].lower() + ''.join(w[:1].upper()+w[1:] for w in words[1:])
    def get(self, name):
        if name in self.map: return self.map[name]
        if self.mode == 'native' or name in ('ながさ','へいほうこん'):
            return name
        if self.mode == 'romaji':
            ws = [self.romaji(name)]
        else:
            ws = [self.eng(w) for w in self.words(name)] or [self.romaji(name)]
        cand = base = self.case(ws) or name
        rsv = RESERVED.get(self.target, set())
        i = 2
        if cand in rsv:
            cand = base + ('_' if self.target == 'py' else 'Fn')
            base = cand
        while cand in self.used or cand in rsv:
            cand = f'{base}{i}'; i += 1
        self.used.add(cand); self.map[name] = cand
        return cand

def map_atom(a, f):
    k = a[0]
    if k == 'fstr': return ('fstr', [(p[0], f(p[1]) if p[0]=='var' else p[1]) for p in a[1]])
    if k == 'logic': return ('logic', a[1], [map_atom(x, f) for x in a[2]])
    if k == 'not': return ('not', map_atom(a[1], f))
    if k == 'var': return ('var', f(a[1]))
    if k == 'idx': return ('idx', f(a[1]), a[2])
    if k == 'key': return ('key', f(a[1]), map_atom(a[2], f))
    if k == 'cmp': return ('cmp', map_atom(a[1], f), a[2], map_atom(a[3], f))
    return a

def map_ir(ir, f):
    out = []
    for depth, n in ir:
        k = n[0]
        if k=='def':        n = (k, f(n[1]), [f(p) for p in n[2]])
        elif k=='forrange': n = (k, f(n[1]), n[2], map_atom(n[3], f), n[4], n[5])
        elif k=='foreach':  n = (k, f(n[1]), f(n[2]), n[3])
        elif k in ('if','elif','while'): n = (k, map_atom(n[1], f))
        elif k=='assign':   n = (k, f(n[1]), map_atom(n[2], f))
        elif k=='assigncall': n = (k, f(n[1]), f(n[2]), [map_atom(a, f) for a in n[3]])
        elif k=='assignext':  n = (k, f(n[1]), n[2], [map_atom(a, f) for a in n[3]])
        elif k=='externcall': n = (k, n[1], [map_atom(a, f) for a in n[2]])
        elif k=='listlit':  n = (k, f(n[1]), [map_atom(a, f) for a in n[2]])
        elif k=='dictlit':  n = (k, f(n[1]), [(map_atom(kk,f), map_atom(vv,f)) for kk,vv in n[2]])
        elif k=='setidx':   n = (k, f(n[1]), n[2], map_atom(n[3], f))
        elif k=='setkey':   n = (k, f(n[1]), map_atom(n[2], f), map_atom(n[3], f))
        elif k in ('delshift','delnull'): n = (k, f(n[1]), n[2])
        elif k=='append':   n = (k, f(n[1]), map_atom(n[2], f))
        elif k=='aug':      n = (k, f(n[1]), n[2], map_atom(n[3], f))
        elif k=='return':   n = (k, map_atom(n[1], f))
        elif k=='print':    n = (k, map_atom(n[1], f))
        elif k=='call':     n = (k, f(n[1]), [map_atom(a, f) for a in n[2]])
        out.append((depth, n))
    return out

BACKENDS = {'py': PyBackend, 'php': PhpBackend, 'js': JsBackend, 'java': JavaBackend}

if __name__ == '__main__':
    target = 'py'
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for a in sys.argv[1:]:
        if a.startswith('--target='): target = a.split('=')[1]
    lang = 'ja'
    for a in sys.argv[1:]:
        if a.startswith('--lang='): lang = a.split('=')[1]
    names = 'native'
    for a in sys.argv[1:]:
        if a.startswith('--names='): names = a.split('=')[1]
    p = Parser(lang=lang)
    ir, colls = p.parse(open(args[0], encoding='utf-8').read())
    if p.errors:
        for e in p.errors: print(e, file=sys.stderr)
        sys.exit(1)
    if names != 'native':
        nm = NameMapper(names, target)
        ir = map_ir(ir, nm.get)
        colls = {nm.get(c) for c in colls}
    code = BACKENDS[target](colls).render(ir)
    if target == 'php': code = php_join_else(code)
    print(code)
