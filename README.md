# UNI — 全母国語プログラミング言語

**母国語で書く。コンパイルすると、既存のプログラミング言語になる。**

```
定義　ごうけいする　￥「上限｛
　「合計　０　から
　FOR　１　「Iが「上限まで　１ずつふえる｛
　　「合計　「I　足す
　最後に「合計渡す

「答え　＝　ごうけいする、１０。
’１から１０の合計：「答え」’　出す。
```

↓ `python3 uni.py program.nihongo --target=php`

```php
<?php
function ごうけいする($上限) {
    $合計 = 0;
    for ($I = 1; $I <= $上限; $I += 1) {
        $合計 += $I;
    }
    return $合計;
}
```

## UNIとは

- **入力側**: 日本語・英語・中国語・アラビア語(対応表15〜20行で母国語を追加できる)
- **核**: 中立AST — パーサはターゲットを知らない
- **出力側**: Python / PHP / JavaScript / Java(バックエンド40〜110行で追加できる)
- **識別子**: `--names=en` で変数・関数名を英語圏の命名規約(snake_case/camelCase)へ自動変換

## 5つの設計原則

1. **IMEフリー** — 全角大文字キーワード(`ＦＯＲ`)・全角記号(`＝、。’「￥`)。日本語入力モードのまま全コードが打てる。全角/半角・大小文字は正規化で同一視
2. **字種判定文法** — 一文字目で品詞が確定: `「`=変数 / `￥「`=引数 / ひらがな=関数 / 全角大文字=制御 / `’`=文字列
3. **閉じない構文** — `「`は閉じない、`{`の閉じは省略可、関数呼び出しに括弧なし(`関数名、引数1、引数2`)
4. **語順自由スロット文法** — マーカー(`から/まで/ずつ`)が格を担い、位置は自由。SOV/SVO・前置/後置の言語差をスロット構造が吸収する
5. **透過3層** — 変換先と互換だから、変換先のエコシステムがそのまま使える(組み込み動詞層+`EX’native.func’`脱出ハッチ)

## クイックスタート

```bash
python3 uni.py examples/fizzbuzz.nihongo --target=py   | python3 -
python3 uni.py examples/seiseki.nihongo  --target=php  > s.php && php s.php
python3 uni.py examples/kuku.nihongo     --target=java > Main.java && javac -encoding UTF-8 Main.java && java Main
```

ブラウザだけで試す: `playground/UNI_playground.html` を開く(依存ゼロ・41KB)。

## リポジトリ構成

```
uni.py                  トランスパイラ本体(パーサ→中立IR→4バックエンド)
frontends/              英語・中国語・アラビア語フロントエンド(対応表方式の実証)
examples/               サンプル+回帰テスト20本(FizzBuzz・九九・成績管理ほか)
playground/             ブラウザPlayground(単一HTML・トランスパイラJS移植内蔵)
editors/vscode/         VSCodeシンタックスハイライト拡張
docs/                   解説ドキュメント
tests/run_matrix.py     回帰マトリクス(全例×全ターゲット意味比較)
```

## 検証状況(v0.4)

- 20プログラム × 4ターゲット 意味一致
- ファジング500件クラッシュ0
- JS移植版(Playground)は生成コードをCLI版とdiff照合済み
- Java向けは型推論を内蔵(int/double/String/List/Map、引数・戻り値・呼び出しキャスト)

## 既知の限界と予定

- `TRY/CATCH`は構文としては共通だが、何が例外を投げるかはターゲット依存(層2の性質)
- `EX’…’`はターゲット固定(移植性と全ライブラリアクセスのトレード)
- クラス構文は未搭載(設計判断は docs/ 参照)

## ライセンス

MIT
