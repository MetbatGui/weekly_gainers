import io
import pandas as pd
import pytest

from application.services.excel_report_builder import ExcelReportBuilder

def test_excel_report_builder_multiple_sheets():
    """ExcelReportBuilder가 전달받은 다중 시트 데이터프레임을 정상적으로 스타일링하여 엑셀 바이너리로 조립하는지 검증"""
    builder = ExcelReportBuilder()

    # 테스트용 데이터프레임 2개 준비
    df_all = pd.DataFrame({
        "종목코드": ["005930", "000660"],
        "종목명": ["삼성전자", "SK하이닉스"],
        "등락률": [21.43, 20.00]
    })
    df_kospi = pd.DataFrame({
        "종목코드": ["005930"],
        "종목명": ["삼성전자"],
        "등락률": [21.43]
    })

    sheets = {
        "전체_등락종목": df_all,
        "KOSPI_200": df_kospi
    }

    # 빌드 실행
    excel_bytes = builder.build_report(sheets)

    # 1. 반환 타입 검증 (bytes)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # 2. 판다스로 엑셀을 다시 읽어 정상 빌드 확인
    excel_file = pd.ExcelFile(io.BytesIO(excel_bytes), engine='openpyxl')
    
    assert "전체_등락종목" in excel_file.sheet_names
    assert "KOSPI_200" in excel_file.sheet_names

    # 3. 데이터 검증
    df_read_all = pd.read_excel(excel_file, sheet_name="전체_등락종목")
    assert len(df_read_all) == 2
    assert df_read_all.iloc[0]["종목명"] == "삼성전자"
    assert df_read_all.iloc[1]["종목명"] == "SK하이닉스"

    df_read_kospi = pd.read_excel(excel_file, sheet_name="KOSPI_200")
    assert len(df_read_kospi) == 1
    assert df_read_kospi.iloc[0]["종목명"] == "삼성전자"
