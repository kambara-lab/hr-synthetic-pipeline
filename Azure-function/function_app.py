import azure.functions as func
import datetime
import json
import logging
import os
import io
import pandas as pd
from azure.storage.blob import BlobServiceClient
import pymssql

SQL_TABLE_COLUMNS = {
    "department_master": ["department_id", "department_name", "division"],
    "employee_master": [
        "employee_id", "name", "gender", "birth_date", "hire_date",
        "department_id", "position", "employment_type", "salary_grade",
    ],
    "evaluation_history": [
        "employee_id", "fiscal_year", "evaluation_grade", "evaluation_score",
    ],
    "attendance_summary": [
        "employee_id", "year_month", "overtime_hours", "absence_days",
        "paid_leave_used_days",
    ],
    "attrition": [
        "employee_id", "attrition_flag", "attrition_date", "attrition_reason_category",
    ],
}


def _get_sql_connection():
    return pymssql.connect(
        server=os.environ["SQL_SERVER"],
        database=os.environ["SQL_DATABASE"],
        user=os.environ["SQL_USER"],
        password=os.environ["SQL_PASSWORD"],
    )


def _clean_value(v):
    """pandasの欠損値(NaN/NA/NaTなど)や空文字列を、SQL用のNoneに正規化する"""
    if pd.isna(v):
        return None
    if isinstance(v, str) and v == "":
        return None
    return v


def _write_df_to_sql(cursor, table_name, df):
    columns = SQL_TABLE_COLUMNS[table_name]

    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"

    records = [
        tuple(_clean_value(row[col]) for col in columns)
        for _, row in df.iterrows()
    ]
    if records:
        cursor.executemany(insert_sql, records)
    logging.info(f"{table_name}: {len(records)}件 書き込み")


def _load_to_sql_database(df_department, df_employee, df_evaluation, df_attendance, df_attrition):
    conn = _get_sql_connection()
    try:
        cursor = conn.cursor()

        # 既存データをクリア(FK制約があるため、子テーブル→親テーブルの順)
        for table in ["evaluation_history", "attendance_summary", "attrition",
                      "employee_master", "department_master"]:
            cursor.execute(f"DELETE FROM {table}")

        # 親テーブルから順に投入
        _write_df_to_sql(cursor, "department_master", df_department)
        _write_df_to_sql(cursor, "employee_master", df_employee)
        _write_df_to_sql(cursor, "evaluation_history", df_evaluation)
        _write_df_to_sql(cursor, "attendance_summary", df_attendance)
        _write_df_to_sql(cursor, "attrition", df_attrition)

        conn.commit()
    finally:
        conn.close()

app = func.FunctionApp()

SOURCE_CONTAINER = "hr-raw-data"
DEST_CONTAINER = "hr-processed-data"


def _read_csv_from_blob(container_client, blob_name):
    blob_client = container_client.get_blob_client(blob_name)
    data = blob_client.download_blob().readall()
    return pd.read_csv(io.BytesIO(data))


@app.route(route="transform", auth_level=func.AuthLevel.FUNCTION)
def transform(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('HRデータ変換処理を開始します。')

    try:
        connection_string = os.environ["STORAGE_CONNECTION_STRING"]
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        source_container = blob_service_client.get_container_client(SOURCE_CONTAINER)

        # 5テーブルを読み込み
        df_department = _read_csv_from_blob(source_container, "department_master.csv")
        df_employee = _read_csv_from_blob(source_container, "employee_master.csv")
        df_evaluation = _read_csv_from_blob(source_container, "evaluation_history.csv")
        df_attendance = _read_csv_from_blob(source_container, "attendance_summary.csv")
        df_attrition = _read_csv_from_blob(source_container, "attrition.csv")

        _load_to_sql_database(df_department, df_employee, df_evaluation, df_attendance, df_attrition)

        # 最新年度の評価だけを抽出
        latest_fy = df_evaluation["fiscal_year"].max()
        df_latest_eval = df_evaluation[df_evaluation["fiscal_year"] == latest_fy][
            ["employee_id", "evaluation_grade", "evaluation_score"]
        ].rename(columns={
            "evaluation_grade": "latest_evaluation_grade",
            "evaluation_score": "latest_evaluation_score",
        })

        # 勤怠を従業員ごとに集計(平均残業時間、合計欠勤・有休)
        df_attendance_agg = df_attendance.groupby("employee_id").agg(
            avg_overtime_hours=("overtime_hours", "mean"),
            total_absence_days=("absence_days", "sum"),
            total_paid_leave_used=("paid_leave_used_days", "sum"),
        ).reset_index()
        df_attendance_agg["avg_overtime_hours"] = df_attendance_agg["avg_overtime_hours"].round(1)

        # 従業員マスタを軸に全部結合
        df_analytics = (
            df_employee
            .merge(df_department, on="department_id", how="left")
            .merge(df_latest_eval, on="employee_id", how="left")
            .merge(df_attendance_agg, on="employee_id", how="left")
            .merge(df_attrition, on="employee_id", how="left")
        )

        # 出力先コンテナーに書き出し
        output_buffer = io.StringIO()
        df_analytics.to_csv(output_buffer, index=False)

        dest_container = blob_service_client.get_container_client(DEST_CONTAINER)
        if not dest_container.exists():
            dest_container.create_container()

        dest_container.upload_blob(
            "hr_analytics_flat.csv",
            output_buffer.getvalue(),
            overwrite=True,
        )

        logging.info(f'変換完了。{len(df_analytics)}件のレコードを出力しました。')

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "records": len(df_analytics),
                "output": f"{DEST_CONTAINER}/hr_analytics_flat.csv",
            }, ensure_ascii=False),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        logging.error(f'エラーが発生しました: {str(e)}')
        return func.HttpResponse(
            json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500,
        )
    