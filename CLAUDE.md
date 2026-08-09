# CLAUDE.md — UNI開発引き継ぎ(Claude Code用)

このリポジトリは **UNI(全母国語プログラミング言語)** のトランスパイラと周辺一式。
文法コア **v0.5**(2026-08-09時点)。このファイルは後続の開発セッション(Claude Code)への引き継ぎ書。

---

## 1. UNIとは(30秒版)

母国語で書き、既存言語(Python/PHP/JS/Java)にトランスパイルされる言語。
本質は「日本語言語」ではなく**中立ASTの二面投影**:

```
[各自然言語ソース] ←対応表← [中立AST] →バックエンド→ [各プログラミング言語]
 日本語/英語/中国語/アラビア語              Python/PHP/JS/Java
```

- 入力側の母国語追加 = 対応表(マーカー表+動詞表)15〜20行
- 出力側の言語追加 = バックエンド40〜110行
- パーサはターゲットを一切知らない(ここが崩れたら設計違反)

## 2. 絶対に守る5原則(変更禁止の設計不変条件)

1. **IMEフリー**: 全コードが日本語入力モードのまま打てる。新構文の記号は必ず日本語モードで一打で出るものから選ぶ。全角/半角・大小文字は正規化で同一視
2. **字種判定**: 一文字目で品詞確定(`「`変数/`￥`役割/ひらがな関数/全角大文字キーワード/`’`文字列/数字)。新構文がこの判定表を曖昧にするなら設計を変えること
3. **閉じない構文**: 開くが閉じない(閉じは`。`・改行・インデント)。明示閉じは例外(`’〜’`、入れ子LLの`」`)で、「明示があれば優先、なければ寛容」
4. **語順自由スロット文法**: 意味はマーカーが担い、位置は自由。位置に意味を載せる構文を足さない(多言語化が壊れる)
5. **中立AST**: パーサにターゲット分岐を書かない。ターゲット差は必ずバックエンド側で吸収

## 3. アーキテクチャ地図

```
uni.py                     本体(1ファイル完結)
 ├ normalize()             正規化(NFKC・漢数字は文脈限定・−→-)
 ├ strip_comment/split_statements
 ├ atom()/datum()/ll_value()  式アトム(タグ付きタプル)
 ├ class Parser            文→中立IRノード列 [(depth, node)]
 │   └ MSG / UniErr        エラー表(ja/en)・行番号つき収集
 ├ class PyBackend         IR→Python(import自動)
 ├ class PhpBackend        IR→PHP(ブロック閉じスタック・is_array実行時判定)
 ├ class JsBackend         IR→JS(let宣言追跡)
 ├ class JavaBackend       IR→Java(★2パス型推論: infer())
 └ class NameMapper        識別子英名変換(--names=en|romaji)

frontends/frontend_{en,zh,ar}.py   対応表→正準形(日本語)→共通Parser
playground/UNI_playground.html    ★トランスパイラのJS完全移植を内蔵(単一HTML)
examples/  *.nihongo 20本+lib.uni  = 回帰テストデータ
tests/run_matrix.py               全例×全ターゲット意味比較(php/node/javac無ければ自動スキップ)
docs/UNI文法書_v0.5.md            構文の正典。「載っていない構文は存在しない」
```

### IRノード種(現在約25)
def / forrange / foreach / if / elif / else / while / try / catch / break / continue /
assign / assigncall / assignext / externcall / listlit / dictlit / setidx / setkey /
delshift / delnull / append / aug / return / print / call

### 式アトム
num / str / fstr / null / var / idx / idxchain / key / listval / dictval / cmp / logic / not / raw

## 4. 開発の作法(このプロジェクト固有)

### 新構文を足すときの手順(必ず全部やる)
1. `docs/UNI文法書_v0.5.md` に構文を書く(正典が先)
2. Parser に規則追加(IRノードを増やすか既存に載せる)
3. **4バックエンド全部**に対応を書く(1つでも欠けたら未完成)
4. Javaは型推論(infer)への影響を必ず確認(新しい値の型は何か)
5. `examples/` にテスト.nihongoを追加
6. `python3 tests/run_matrix.py` 全通過を確認
7. **playground/UNI_playground.html のJSエンジンにも同じ変更を移植**(CLI版とJS版は二重実装。移植後、生成コードdiffで照合するのが慣例)
8. 文法書のPlayground内タブ(GRAMMAR定数)も更新

### 回帰の鉄則
- 回帰比較は**両ファイル非空を前提条件に含める**(過去、空ファイル同士のdiffで偽陽性を出した事故あり)
- 出力比較は意味比較(norm関数: クォート・空白・.0・null表記を正規化)

### 過去に踏んだ地雷(再発注意)
- **`\b?`はPythonでもJSでも不正な正規表現**(nothing to repeat)。`(?:\s+|(?=…)|$)`等で代替
- 漢数字正規化は識別子を壊す(`「一部`→`1部`事故)。文脈限定(個目/つ目/番目直前 or 単独)を崩さない
- FOR終値の正規表現は先にループ変数部(`「〜が`)を除去してから探す(`「Iが10まで`を丸ごと食う事故)
- 前置マーカー(英語・アラビア語等)は**語境界`\b`必須+長い複合句を先に適用**(كل⊂كلي衝突、أكبر منのمن先食い事故)
- USEの取込はnormalizeの**前**に行う(取込ファイルが未正規化になる事故)
- Java: 変数→変数代入の型伝播、Object源のaugはdouble昇格+Numberキャスト、引数はcall-site側でintValue()/doubleValue()キャスト
- パッチをsed/replaceで当てるとき、対象文字列のエスケープ差で**無音で不発**することがある。適用後は必ずassertかgrepで確認

### コード規約
- コード・コメント・コミットメッセージに個人名・社名・案件情報を書かない
- 生成コードの可読性は品質要件(人が書いたように見えること)。4言語とも日本語識別子ネイティブ対応を活用
- エラーメッセージは必ずMSG表(ja/en)経由。直書き禁止(エラーも対応表方式)

## 5. 動作確認コマンド

```bash
# 変換
python3 uni.py examples/seiseki.nihongo --target=py
python3 uni.py examples/fizzbuzz.nihongo --target=java --names=en

# 全回帰(php/node/javacが無いターゲットは自動スキップ)
python3 tests/run_matrix.py

# 多言語フロントエンド
python3 frontends/frontend_en.py examples/test3_en.prog
python3 frontends/frontend_zh.py examples/test3_zh.prog
python3 frontends/frontend_ar.py examples/test3_ar.prog

# Playground: playground/UNI_playground.html をブラウザで開くだけ(依存ゼロ)
```

## 6. ロードマップ(v0.6候補・優先順)

1. **なでしこ実プログラムの本格移植**(古典FizzBuzz/九九は済。次は数十〜百行級の実物で破綻点探し)
2. LLリテラルの3段以上の入れ子の保証+ファジング拡充
3. 英名変換の語彙表拡充(現40語)・第3言語辞書(--names=es等)
4. Rust/C追加の検討(=層3・注釈系の設計が必要。EXの拡張から入るのが筋)
5. VSCode拡張の配布(vsce package)・Playgroundのホスティング
6. クラス構文: **v1では入れない判断済み**(理由はNotion参照)。要望が実際に出てから「かた」(最小レコード+関数束)として再検討

## 7. 判断保留・優大さんに聞くこと

- `「それ`(暗黙ループ要素名)の正式名(現状は仮採用)
- クラス構文判断への拒否権行使の有無
- 最初のユーザー像の最終決定(提案: 日本語で考えたい実務プログラマ→研修市場)
- L2.3内のプロジェクト位置づけ(意図的に未決)

## 8. 記録の場所

- 全設計判断の経緯: Notion「UNI — 全母国語プログラミング言語」ページ(ID: 3a3b359164e3819485daecfef1d85689)。**設計変更したら必ずここに追記**(single source of truth)
- 構文の正典: docs/UNI文法書_v0.5.md
- 思想と背景: docs/UNI解説ドキュメント_v0.4.md(なでしこ敗因分析・透過3層モデル)

---
*引き継ぎ元: claude.ai UNIプロジェクトセッション(2026-07-20誕生〜2026-08-09 v0.5)*
