"""上りパッケージ（子機→母艦）の取り込み（転送仕様書 第4章）。

冪等であること：同じファイルを何度取り込んでも結果は変わらない。
更新は、受信した updatedAt が母艦側より新しい場合だけ行う（母艦での編集を守る）。
未知のマスタIDを参照する記録は、拒否せず未分類として受け入れる。
"""

from __future__ import annotations

import logging
import sqlite3

from ...core import clock
from ...db.connection import transaction
from ...domain.models import ImportResult
from ...repositories.mistakes import MistakeRepository
from ...repositories.quotas import QuotaRepository
from ...repositories.sessions import SessionRepository
from ...repositories.transfer import DeviceRepository, ImportedPackageRepository
from ..master_service import MasterService
from ..review_service import ReviewService
from ..settings_service import SettingsService
from . import validator

log = logging.getLogger(__name__)


class UpImporter:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        settings: SettingsService,
        masters: MasterService,
        sessions: SessionRepository,
        mistakes: MistakeRepository,
        quotas: QuotaRepository,
        devices: DeviceRepository,
        imported: ImportedPackageRepository,
        reviews: ReviewService,
    ) -> None:
        self.conn = conn
        self.settings = settings
        self.masters = masters
        self.sessions = sessions
        self.mistakes = mistakes
        self.quotas = quotas
        self.devices = devices
        self.imported = imported
        self.reviews = reviews

    # --- マスタIDの解決 -----------------------------------------------------

    def _known_exam(self, exam_id: str | None) -> str | None:
        return exam_id if exam_id and self.masters.exams.exists(exam_id) else None

    def _known_material(self, material_id: str | None, exam_id: str | None) -> str | None:
        if not material_id or not self.masters.materials.exists(material_id):
            return None
        material = self.masters.materials.get(material_id)
        if material and exam_id and material.exam_id != exam_id:
            return None
        return material_id

    def _known_subject(self, subject_id: str | None, exam_id: str | None) -> str | None:
        if not subject_id or not self.masters.subjects.exists(subject_id):
            return None
        subject = self.masters.subjects.get(subject_id)
        if subject and exam_id and subject.exam_id != exam_id:
            return None
        return subject_id

    # --- 取り込み -----------------------------------------------------------

    def import_package(self, package: dict, *, validate: bool = True) -> ImportResult:
        if validate:
            validator.validate(package, "up").raise_if_bad()

        package_id = package["packageId"]
        device_id = package.get("deviceId")
        device_name = package.get("deviceName", "")
        records = package.get("records", {})

        result = ImportResult(
            package_id=package_id,
            device_id=device_id,
            device_name=device_name,
            already_imported=self.imported.was_imported(package_id),
        )

        with transaction(self.conn):
            for session in records.get("sessions", []):
                self._import_session(session, device_id, result)
            for mistake in records.get("mistakes", []):
                self._import_mistake(mistake, device_id, result)
            for entry in records.get("reviewResults", []):
                self._import_review_result(entry, result)
            for status in records.get("quotaStatus", []):
                self._import_quota_status(status, result)

            if device_id:
                self.devices.upsert(device_id, device_name, package_id)
            self.imported.record(package_id, device_id, package.get("includedIds", []))

        log.info("上りパッケージを取り込んだ: %s (%s)", package_id, result.summary())
        return result

    # --- レコードごと -------------------------------------------------------

    def _is_newer(self, table_row: sqlite3.Row | None, updated_at: str) -> bool:
        return table_row is None or updated_at > table_row["updated_at"]

    def _import_session(self, payload: dict, device_id: str | None, result: ImportResult) -> None:
        record_id = payload["id"]
        updated_at = clock.to_db(clock.parse_iso(payload["updatedAt"]))
        existing = self.sessions.row(record_id)
        if not self._is_newer(existing, updated_at):
            result.skipped += 1
            if existing is not None and existing["unclassified"]:
                result.unclassified += 1
            return

        exam_id = self._known_exam(payload.get("examId"))
        material_id = self._known_material(payload.get("materialId"), exam_id)
        subject_id = self._known_subject(payload.get("subjectId"), exam_id)
        unclassified = bool(payload.get("unclassified")) or exam_id is None

        started_at = clock.parse_iso(payload["startedAt"])
        range_value = payload.get("range") or {}
        deleted = bool(payload.get("deleted"))

        values = {
            "exam_id": exam_id,
            "material_id": material_id,
            "subject_id": subject_id,
            "quota_id": payload.get("quotaId"),
            "unclassified": 1 if unclassified else 0,
            "started_at": clock.to_db(started_at),
            "ended_at": clock.to_db(clock.parse_iso(payload["endedAt"])),
            "active_seconds": int(payload.get("activeSeconds", 0)),
            "study_date": clock.study_date_str(started_at, self.settings.day_change_hour),
            "range_unit": range_value.get("unit"),
            "range_from": range_value.get("from"),
            "range_to": range_value.get("to"),
            "correct": payload.get("correct"),
            "attempted": payload.get("attempted"),
            "focus": payload.get("focus"),
            "memo": payload.get("memo", ""),
            "entry_mode": payload.get("entryMode", "timer"),
            "source": "satellite",
            "device_id": device_id,
            "updated_at": updated_at,
            "deleted_at": updated_at if deleted else None,
        }

        if existing is None:
            created_at = clock.to_db(clock.parse_iso(payload.get("createdAt", payload["updatedAt"])))
            self.sessions.insert({**values, "created_at": created_at}, record_id=record_id)
            result.added += 1
        else:
            self.sessions.update(record_id, values, touch=False)
            result.updated += 1

        # 子機で範囲まで進めた分を、参考書の現在位置にも反映する
        if material_id and values["range_to"] and not deleted:
            self.masters.materials.advance_current(material_id, values["range_to"])

        if unclassified and not deleted:
            result.unclassified += 1

    def _import_mistake(self, payload: dict, device_id: str | None, result: ImportResult) -> None:
        record_id = payload["id"]
        updated_at = clock.to_db(clock.parse_iso(payload["updatedAt"]))
        existing = self.mistakes.row(record_id)
        if not self._is_newer(existing, updated_at):
            result.skipped += 1
            return

        exam_id = self._known_exam(payload.get("examId"))
        session_id = payload.get("sessionId")
        if session_id and self.sessions.row(session_id) is None:
            session_id = None  # 外部キーに引っかからないよう、知らない記録への参照は外す
        deleted = bool(payload.get("deleted"))

        values = {
            "session_id": session_id,
            "exam_id": exam_id,
            "material_id": self._known_material(payload.get("materialId"), exam_id),
            "subject_id": self._known_subject(payload.get("subjectId"), exam_id),
            "question_ref": payload.get("questionRef", ""),
            "memo": payload.get("memo", ""),
            "reason": payload.get("reason"),
            "source": "satellite",
            "device_id": device_id,
            "updated_at": updated_at,
            "deleted_at": updated_at if deleted else None,
        }

        if existing is None:
            created_at = clock.to_db(clock.parse_iso(payload.get("createdAt", payload["updatedAt"])))
            schedule = self.reviews.initial_schedule(
                clock.study_date(clock.parse_iso(payload["createdAt"]), self.settings.day_change_hour)
                if payload.get("createdAt")
                else None
            )
            self.mistakes.insert(
                {**values, **schedule, "created_at": created_at}, record_id=record_id
            )
            result.added += 1
        else:
            self.mistakes.update(record_id, values, touch=False)
            result.updated += 1
        if exam_id is None and not deleted:
            result.unclassified += 1

    def _import_review_result(self, payload: dict, result: ImportResult) -> None:
        added = self.reviews.record_result(
            result_id=payload["id"],
            mistake_id=payload["mistakeId"],
            result=payload["result"],
            reviewed_at=clock.parse_iso(payload["reviewedAt"]),
            source="satellite",
        )
        if added:
            result.added += 1
        else:
            result.skipped += 1

    def _import_quota_status(self, payload: dict, result: ImportResult) -> None:
        updated_at = clock.to_db(clock.parse_iso(payload["updatedAt"]))
        applied = self.quotas.apply_status(
            payload["quotaId"], payload["status"], payload["id"], updated_at
        )
        if applied:
            result.updated += 1
        else:
            result.skipped += 1
