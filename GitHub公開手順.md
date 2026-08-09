# GitHub公開手順(このフォルダから)

```bash
cd uni-repo
git init
git add .
git commit -m "UNI v0.4: 全母国語プログラミング言語 初公開"
# GitHubで新規リポジトリ(例: uni-lang)を作成してから:
git remote add origin https://github.com/<あなたのユーザー名>/uni-lang.git
git branch -M main
git push -u origin main
```

- コミット前に `python3 tests/run_matrix.py` で全回帰が通ることを確認
- LICENSEのCopyright表記は必要に応じて自分の名義に変更
- リポジトリ名・説明文・トピック(japanese, transpiler, programming-language)は自由に
