# HRアナリティクス疑似データセット

コア人事システムからの抽出を模した、正規化済み複数テーブル構成の疑似データセットです。
Azure上でのHRアナリティクス・パイプライン(Blob Storage → Functions →
SQL Database Serverless → Power BI)のデモ用に生成しました。

実在の個人・組織とは一切関係のない、統計的に生成した架空データです。

## パイプライン実装状況

| コンポーネント | 状態 | 内容 |
|---|---|---|
| Blob Storage | ✅ 実装済み | 疑似データセット(CSV5ファイル)を`hr-raw-data`コンテナーに格納 |
| Function App | ✅ 実装済み | Python 3.12・Flex従量課金プラン。5テーブルの読み込み・変換・SQL Database書き込みを実行(コードは`Azure-function/`配下) |
| SQL Database | ✅ 実装済み | Serverlessティア。5テーブルを正規化したまま格納(FK制約あり) |
| Power BI | ✅ 実装済み | SQL Databaseと直接接続し、リレーションシップを自動検出。全社サマリ／離職分析／評価×勤怠分析の3ページ構成 |
| CI/CD自動化 | 🔲 未着手 | 現状は手動デプロイ(`func azure functionapp publish`)。将来的にGitHub Actions等での自動化を検討中 |

## なぜ単一のフラットCSVではなく5テーブルに分割したか

実務のコア人事システムからのデータ抽出は、基本的に正規化されたテーブル群として
出力されます。単一の分析用フラットファイルを最初から用意してしまうと、
「ETLで結合・変換する」という工程そのものが再現できません。このデータセットでは
あえて正規化した状態で生成し、Functions側での**JOIN・集計・非正規化(analytics-ready化)**
の設計判断を見せられるようにしています。

さらに、SQL Database側も正規化した5テーブルのまま格納する設計にしました。理由は、
Power BI側でリレーションシップ(スタースキーマ)を組んでモデリングする、という
実務でよくあるパターン(SQL/DWHは正規化のまま持ち、BI層でモデリングする)を
再現するためです。

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

SQL Database側も同じER構成のまま、外部キー制約付きで格納しています。

## Azure Function App(`Azure-function/`)

Blob Storageから5テーブルを読み込み、SQL Databaseへの書き込みとBlobへのanalytics-ready
フラットCSV出力の両方を行うHTTPトリガー関数です。

- **接続ライブラリにpymssqlを採用**:Flex従量課金プラン(Linux)はrootアクセスがなく、
  `pyodbc`が要求するODBC Driverを追加インストールできないため、単体で動く`pymssql`を選択
- **書き込みは洗い替え(full refresh)方式**:実行のたびに既存データを`DELETE`してから
  再投入する設計。冪等性を確保し、複数テーブルへの書き込みは1トランザクションにまとめて
  途中失敗時のロールバックを保証
- **NaN/空文字列の正規化**:`pd.isna()`ベースの判定でSQL用のNULLに変換

## 生成ロジックの設計ポイント

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

## 関連リンク

- 構築の過程で得た気づきは [note](https://note.com/kambaralab) で連載中
- 技術的な深掘り記事は [kambaralab.com](https://kambaralab.com) にて公開予定