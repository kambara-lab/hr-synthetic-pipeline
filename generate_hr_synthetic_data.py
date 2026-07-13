# -*- coding: utf-8 -*-
"""
HRアナリティクス・クラウドパイプライン用 疑似データセット生成スクリプト
=====================================================================

目的:
  実際のコア人事システムからの抽出を模した「正規化済み複数テーブル」構成の
  疑似データセットを生成する。単一のフラットCSVではなく、以下5テーブルに
  分割することで、Azure Data Factory / Functions での結合(JOIN)・変換処理を
  デモする材料にする。

生成されるテーブル:
  1. department_master.csv   部署マスタ
  2. employee_master.csv     従業員マスタ
  3. evaluation_history.csv  人事評価履歴(年度別)
  4. attendance_summary.csv  勤怠サマリ(月次)
  5. attrition.csv           離職情報

再現性:
  乱数シードを固定しているため、何度実行しても同じデータセットが生成される。
  (ブログ/READMEで「再現可能な検証環境」であることを明記できる)

注意:
  全て統計的に妥当な範囲で自動生成した架空データであり、実在の個人・組織とは
  一切関係ない。
"""

import random
from datetime import date, timedelta

import pandas as pd
from faker import Faker

SEED = 20260713
random.seed(SEED)
fake = Faker("ja_JP")
Faker.seed(SEED)

N_EMPLOYEES = 600
FISCAL_YEARS = [2023, 2024, 2025]
ATTENDANCE_MONTHS = pd.period_range("2025-01", "2025-12", freq="M")

# ---------------------------------------------------------------------------
# 1. 部署マスタ
# ---------------------------------------------------------------------------
divisions = ["営業本部", "技術本部", "管理本部", "人事本部", "生産本部"]
department_rows = []
dept_id = 1
for div in divisions:
    n_depts = random.randint(2, 4)
    for i in range(n_depts):
        department_rows.append(
            {
                "department_id": f"D{dept_id:03d}",
                "department_name": f"{div}{['第一', '第二', '第三', '第四'][i]}部",
                "division": div,
            }
        )
        dept_id += 1

df_department = pd.DataFrame(department_rows)

# ---------------------------------------------------------------------------
# 2. 従業員マスタ
# ---------------------------------------------------------------------------
positions = ["一般", "主任", "係長", "課長", "部長"]
position_weights = [0.45, 0.20, 0.15, 0.13, 0.07]
employment_types = ["正社員", "契約社員", "派遣社員"]
employment_weights = [0.80, 0.13, 0.07]
salary_grades = ["G1", "G2", "G3", "G4", "G5", "G6"]

employee_rows = []
today = date(2025, 12, 31)

for i in range(1, N_EMPLOYEES + 1):
    emp_id = f"E{i:05d}"
    gender = random.choice(["M", "F"])
    name = fake.name_male() if gender == "M" else fake.name_female()

    age = int(random.gauss(38, 9))
    age = max(22, min(60, age))
    birth_date = today - timedelta(days=age * 365 + random.randint(0, 364))

    tenure_years = random.randint(0, min(age - 22, 30))
    hire_date = today - timedelta(days=tenure_years * 365 + random.randint(0, 364))

    dept = df_department.sample(1, random_state=random.randint(0, 10_000)).iloc[0]

    # 勤続年数・年齢が高いほど役職が上がりやすいよう補正
    pos_weights_adj = position_weights.copy()
    if tenure_years >= 10:
        pos_weights_adj = [0.20, 0.20, 0.25, 0.25, 0.10]
    elif tenure_years >= 5:
        pos_weights_adj = [0.35, 0.25, 0.20, 0.15, 0.05]

    position = random.choices(positions, weights=pos_weights_adj, k=1)[0]
    employment_type = random.choices(
        employment_types, weights=employment_weights, k=1
    )[0]
    salary_grade = random.choices(
        salary_grades, weights=[0.10, 0.20, 0.25, 0.20, 0.15, 0.10], k=1
    )[0]

    employee_rows.append(
        {
            "employee_id": emp_id,
            "name": name,
            "gender": gender,
            "birth_date": birth_date.isoformat(),
            "hire_date": hire_date.isoformat(),
            "department_id": dept["department_id"],
            "position": position,
            "employment_type": employment_type,
            "salary_grade": salary_grade,
        }
    )

df_employee = pd.DataFrame(employee_rows)

# ---------------------------------------------------------------------------
# 3. 人事評価履歴(年度別)
# ---------------------------------------------------------------------------
grade_map = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
evaluation_rows = []

for emp_id in df_employee["employee_id"]:
    base_tendency = random.gauss(0, 1)  # 個人の評価の出やすさ傾向
    for fy in FISCAL_YEARS:
        score = base_tendency + random.gauss(0, 0.8)
        if score > 1.2:
            grade = "S"
        elif score > 0.4:
            grade = "A"
        elif score > -0.4:
            grade = "B"
        elif score > -1.2:
            grade = "C"
        else:
            grade = "D"
        evaluation_rows.append(
            {
                "employee_id": emp_id,
                "fiscal_year": fy,
                "evaluation_grade": grade,
                "evaluation_score": grade_map[grade],
            }
        )

df_evaluation = pd.DataFrame(evaluation_rows)

# ---------------------------------------------------------------------------
# 4. 勤怠サマリ(月次、2025年の12ヶ月分)
# ---------------------------------------------------------------------------
attendance_rows = []
for emp_id, position in zip(df_employee["employee_id"], df_employee["position"]):
    # 役職が上がるほど残業時間が増える傾向(管理職の労務課題を反映)
    base_overtime = {"一般": 12, "主任": 18, "係長": 22, "課長": 28, "部長": 20}[
        position
    ]
    for ym in ATTENDANCE_MONTHS:
        overtime = max(0, round(random.gauss(base_overtime, 8), 1))
        absence = max(0, int(random.gauss(0.5, 1.0)))
        paid_leave = max(0, min(20, int(random.gauss(1.0, 1.2))))
        attendance_rows.append(
            {
                "employee_id": emp_id,
                "year_month": str(ym),
                "overtime_hours": overtime,
                "absence_days": absence,
                "paid_leave_used_days": paid_leave,
            }
        )

df_attendance = pd.DataFrame(attendance_rows)

# ---------------------------------------------------------------------------
# 5. 離職情報
# ---------------------------------------------------------------------------
attrition_reasons = ["転職", "家庭事情", "定年", "契約満了", "その他"]
attrition_rows = []

# 全体の離職率をおおむね12%程度に設定
attrited_ids = set(
    random.sample(list(df_employee["employee_id"]), k=int(N_EMPLOYEES * 0.12))
)

for emp_id in df_employee["employee_id"]:
    if emp_id in attrited_ids:
        attrition_date = today - timedelta(days=random.randint(30, 700))
        attrition_rows.append(
            {
                "employee_id": emp_id,
                "attrition_flag": "Y",
                "attrition_date": attrition_date.isoformat(),
                "attrition_reason_category": random.choice(attrition_reasons),
            }
        )
    else:
        attrition_rows.append(
            {
                "employee_id": emp_id,
                "attrition_flag": "N",
                "attrition_date": "",
                "attrition_reason_category": "",
            }
        )

df_attrition = pd.DataFrame(attrition_rows)

# ---------------------------------------------------------------------------
# 出力(Excelで文字化けしないよう UTF-8 with BOM で保存)
# ---------------------------------------------------------------------------
import os

OUT_DIR = "/mnt/user-data/outputs/hr_synthetic_dataset"
os.makedirs(OUT_DIR, exist_ok=True)

tables = {
    "department_master.csv": df_department,
    "employee_master.csv": df_employee,
    "evaluation_history.csv": df_evaluation,
    "attendance_summary.csv": df_attendance,
    "attrition.csv": df_attrition,
}

for filename, df in tables.items():
    path = os.path.join(OUT_DIR, filename)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"{filename}: {len(df)} rows -> {path}")

print("\n=== 完了 ===")
