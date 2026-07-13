# HRアナリティクス疑似データセット

コア人事システムからの抽出を模した、正規化済み複数テーブル構成の疑似データセットです。
Azure上でのHRアナリティクス・パイプライン(Blob Storage → Data Factory/Functions →
SQL Database Serverless → Power BI)のデモ用に生成しました。

実在の個人・組織とは一切関係のない、統計的に生成した架空データです。

## なぜ単一のフラットCSVではなく5テーブルに分割したか

実務のコア人事システムからのデータ抽出は、基本的に正規化されたテーブル群として
出力されます。単一の分析用フラットファイルを最初から用意してしまうと、
「ETLで結合・変換する」という工程そのものが再現できません。このデータセットでは
あえて正規化した状態で生成し、Data Factory / Functions 側での **JOIN・集計・
非正規化(analytics-ready化)** の設計判断を見せられるようにしています。

## テーブル構成

| ファイル | 行数 | 内容 | 主キー |
|---|---|---|---|
| `department_master.csv` | 16 | 部署マスタ(本部・部) | department_id |
| `employee_master.csv` | 600 | 従業員マスタ(属性・所属・役職) | employee_id |
| `evaluation_history.csv` | 1,800 | 年度別人事評価(2023〜2025年度) | employee_id + fiscal_year |
| `attendance_summary.csv` | 7,200 | 月次勤怠サマリ(2025年1〜12月) | employee_id + year_month |
| `attrition.csv` | 600 | 離職フラグ・離職理由 | employee_id |

### ER関係(概略)

```
department_master ──┬─< employee_master ──┬─< evaluation_history
                     │                      ├─< attendance_summary
                     │                      └─< attrition
```

## 生成ロジックの設計ポイント(README/ブログでそのまま使える説明)

- **役職と勤続年数の相関**:勤続年数が長いほど上位役職になりやすいよう重み付け
  (完全ランダムではなく、実データっぽい歪みを持たせている)
- **役職と残業時間の相関**:課長職の残業時間が最も長くなるよう設定
  (管理職の労務課題という、実務でよくある論点をデータに反映)
- **個人の評価傾向**:従業員ごとに「評価の出やすさ」の基準値を持たせ、年度間で
  完全独立ではなく緩やかな相関を持つ評価スコアを生成
- **離職率**:全体の約12%を離職に設定し、離職予測系の分析(ロジスティック回帰・
  決定木など)のデモにも使える設計

## 再現性

`generate_hr_synthetic_data.py` は乱数シードを固定しているため、同じ環境で
再実行すれば全く同じデータセットが再生成されます。

```bash
pip install faker pandas --break-system-packages
python3 generate_hr_synthetic_data.py
```

## 文字コードについて

全CSVは `utf-8-sig` (UTF-8 with BOM) で出力しています。Excelで直接開いても
日本語が文字化けしません。
