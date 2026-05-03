import os
import json
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_CARS      = "Cars"
SHEET_INCIDENTS = "Incidents"


class SheetsDB:
    def __init__(self):
        self._client      = None
        self._spreadsheet = None
        self._sheet_id    = os.environ.get("GOOGLE_SHEET_ID")

    def _get_client(self):
        if self._client is None:
            creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
            creds_file = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
            if creds_json:
                creds = Credentials.from_service_account_info(
                    json.loads(creds_json), scopes=SCOPES)
            else:
                creds = Credentials.from_service_account_file(
                    creds_file, scopes=SCOPES)
            self._client = gspread.authorize(creds)
        return self._client

    def _get_spreadsheet(self):
        if self._spreadsheet is None:
            self._spreadsheet = self._get_client().open_by_key(self._sheet_id)
            self._ensure_sheets()
        return self._spreadsheet

    def _ensure_sheets(self):
        existing = [ws.title for ws in self._spreadsheet.worksheets()]
        if SHEET_CARS not in existing:
            ws = self._spreadsheet.add_worksheet(title=SHEET_CARS, rows=1000, cols=6)
            ws.append_row(["plate", "user_id", "username", "full_name", "registered_at"])
        if SHEET_INCIDENTS not in existing:
            ws = self._spreadsheet.add_worksheet(title=SHEET_INCIDENTS, rows=1000, cols=7)
            ws.append_row(["timestamp", "plate", "reason", "reporter_id",
                           "reporter_name", "has_photo", "owner_notified"])

    def _cars(self):
        return self._get_spreadsheet().worksheet(SHEET_CARS)

    def _incidents(self):
        return self._get_spreadsheet().worksheet(SHEET_INCIDENTS)

    def register_car(self, plate, user_id, username, full_name):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._cars().append_row([plate, user_id, username, full_name, now])
            return True
        except Exception as e:
            logger.error(f"register_car: {e}")
            return False

    def find_owner(self, plate):
        try:
            for row in self._cars().get_all_records():
                if str(row.get("plate", "")).upper() == plate.upper():
                    return {
                        "plate":     row["plate"],
                        "user_id":   str(row["user_id"]),
                        "username":  row.get("username", ""),
                        "full_name": row.get("full_name", ""),
                    }
        except Exception as e:
            logger.error(f"find_owner: {e}")
        return None

    def get_cars_by_user(self, user_id):
        try:
            return [
                row["plate"]
                for row in self._cars().get_all_records()
                if str(row.get("user_id", "")) == str(user_id)
            ]
        except Exception as e:
            logger.error(f"get_cars_by_user: {e}")
            return []

    def remove_car(self, plate, user_id):
        try:
            records = self._cars().get_all_records()
            for i, row in enumerate(records, start=2):
                if (str(row.get("plate", "")).upper() == plate.upper()
                        and str(row.get("user_id", "")) == str(user_id)):
                    self._cars().delete_rows(i)
                    return True
        except Exception as e:
            logger.error(f"remove_car: {e}")
        return False

    def log_incident(self, plate, reason, reporter_id, reporter_name, has_photo):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._incidents().append_row([
                now, plate, reason, reporter_id,
                reporter_name, "Так" if has_photo else "Ні", "Так"
            ])
            return True
        except Exception as e:
            logger.error(f"log_incident: {e}")
            return False
