import os
import io
from typing import Optional
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

from dotenv import load_dotenv
from domain.ports import CloudUploadPort

load_dotenv()

class GoogleDriveAdapter(CloudUploadPort):
    """Google Drive에 주간 리포트(Excel)를 저장하는 어댑터."""

    SCOPES = ['https://www.googleapis.com/auth/drive']

    def __init__(self, token_file: str = "secrets/token.json"):
        """GoogleDriveAdapter 초기화.
        
        Args:
            token_file (str): OAuth 2.0 Token JSON 파일 경로.
        """
        self.token_file = token_file
        self.root_folder_id = os.getenv("GOOGLE_DRIVE_WEEKLY_CHANGE_FOLDER_ID")
        
        if not os.path.exists(self.token_file):
             raise FileNotFoundError(f"Token file not found: {self.token_file}. secrets 폴더에 토큰이 있는지 확인해주세요.")

        self.drive_service = self._authenticate()
        print(f"[Adapter:GoogleDrive] 인증 완료 (Root Folder ID: {self.root_folder_id})")

    def _authenticate(self):
        """Google Drive API 인증 및 토큰 갱신."""
        try:
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
            
            if creds and creds.expired and creds.refresh_token:
                print("[Adapter:GoogleDrive] 토큰 만료, 갱신 시도...")
                creds.refresh(Request())
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                    
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            raise RuntimeError(f"Google Drive 인증 실패: {e}")

    def _get_or_create_folder(self, folder_name: str, parent_id: str) -> str:
        """폴더가 존재하면 ID를 반환하고, 없으면 생성합니다."""
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
        results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if files:
            return files[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            print(f"[Adapter:GoogleDrive] New folder created: {folder_name}")
            return file.get('id')

    def _ensure_path(self, path: str) -> str:
        """경로상의 폴더들을 모두 생성하고 마지막 폴더의 ID를 반환합니다."""
        current_parent_id = self.root_folder_id or 'root'
        if not path or path.strip("/") == "":
            return current_parent_id

        parts = path.strip("/").split("/")
        for part in parts:
            current_parent_id = self._get_or_create_folder(part, current_parent_id)
            
        return current_parent_id

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        """로컬 파일을 구글 드라이브에 업로드합니다."""
        try:
            if not os.path.exists(local_path):
                print(f"[Adapter:GoogleDrive] [Error] Local file not found: {local_path}")
                return False

            # 1. 업로드 위치(부모 폴더) 확보
            parent_id = self._ensure_path(remote_path)

            # 2. 기존 파일 존재 여부 확인 (있으면 덮어쓰기)
            query = f"name = '{filename}' and '{parent_id}' in parents and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id)").execute()
            existing_files = results.get('files', [])

            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True)

            if existing_files:
                file_id = existing_files[0]['id']
                self.drive_service.files().update(fileId=file_id, media_body=media).execute()
                print(f"[Adapter:GoogleDrive] [OK] File updated: {filename}")
            else:
                file_metadata = {'name': filename, 'parents': [parent_id]}
                self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                print(f"[Adapter:GoogleDrive] [OK] File uploaded: {filename}")

            return True
        except Exception as e:
            print(f"[Adapter:GoogleDrive] [Error] File upload failed: {e}")
            return False

    def upload_excel(self, df: pd.DataFrame, remote_path: str, filename: str) -> bool:
        """DataFrame을 Excel로 변환하여 구글 드라이브에 업로드합니다."""
        try:
            # 1. 메모리 내 엑셀 파일 생성
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='WeeklyGainers')
                
                # 가독성 개선: 열 너비 자동 조절
                worksheet = writer.sheets['WeeklyGainers']
                for i, col in enumerate(df.columns):
                    column_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
                    worksheet.set_column(i, i, column_len)
                
            output.seek(0)

            # 2. 업로드 위치(부모 폴더) 확보
            parent_id = self._ensure_path(remote_path)

            # 3. 기존 파일 존재 여부 확인 (있으면 덮어쓰기)
            query = f"name = '{filename}' and '{parent_id}' in parents and trashed = false"
            results = self.drive_service.files().list(q=query, fields="files(id)").execute()
            existing_files = results.get('files', [])

            media = MediaIoBaseUpload(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)

            if existing_files:
                file_id = existing_files[0]['id']
                self.drive_service.files().update(fileId=file_id, media_body=media).execute()
                print(f"[Adapter:GoogleDrive] [OK] File updated: {filename}")
            else:
                file_metadata = {'name': filename, 'parents': [parent_id]}
                self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                print(f"[Adapter:GoogleDrive] [OK] File uploaded: {filename}")

            return True
        except Exception as e:
            print(f"[Adapter:GoogleDrive] [Error] Upload failed: {e}")
            return False
