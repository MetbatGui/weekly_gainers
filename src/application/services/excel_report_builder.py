import io
from typing import Dict
import pandas as pd

class ExcelReportBuilder:
    """Pandas DataFrame들을 입력받아 가독성 스타일이 적용된 Excel 바이너리 데이터를 생성하는 빌더 서비스."""

    def build_report(self, sheets: Dict[str, pd.DataFrame]) -> bytes:
        """주어진 시트명과 데이터프레임 딕셔너리로 Excel 바이너리(bytes)를 빌드합니다."""
        output = io.BytesIO()
        
        # xlsxwriter 엔진을 활용하여 메모리에 엑셀 생성
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # 1. 헤더 셀 스타일 정의 (가독성 높은 연한 파란색 배경)
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'vcenter',
                'align': 'center',
                'fg_color': '#D9E1F2',  # 연한 파랑
                'border': 1
            })
            
            # 데이터 행 보더 포맷 정의
            data_format = workbook.add_format({
                'border': 1
            })
            
            for sheet_name, df in sheets.items():
                df.to_excel(writer, index=False, sheet_name=sheet_name)
                worksheet = writer.sheets[sheet_name]
                
                # 2. 헤더 행 덮어쓰기 (스타일 적용)
                for col_num, col_name in enumerate(df.columns):
                    worksheet.write(0, col_num, col_name, header_format)
                    
                # 3. 열 너비 자동 설정 및 데이터 보더 적용
                for col_num, col_name in enumerate(df.columns):
                    # 해당 컬럼의 모든 데이터 값을 문자열로 변환하여 최대 길이를 측정
                    if len(df) > 0:
                        # 한글의 경우 바이트나 길이에 따라 가독성을 더 넓게 확보해야 할 수 있으므로 여유 있게 패딩
                        max_len = df[col_name].astype(str).str.len().max()
                    else:
                        max_len = 0
                        
                    # 헤더 명칭과 데이터 최대 길이 중 큰 값을 선택하고 패딩(+4) 적용
                    column_width = max(max_len, len(col_name)) + 4
                    worksheet.set_column(col_num, col_num, column_width)
                    
                # 4. 추가 행 높이 설정 (헤더 행은 조금 더 넓게 설정)
                worksheet.set_row(0, 25) # 헤더 높이 25
                
        output.seek(0)
        return output.getvalue()
