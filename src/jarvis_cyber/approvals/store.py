from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from jarvis_cyber.core.schemas import ToolApprovalRequest, ToolApprovalStatus
from jarvis_cyber.storage.database import database


class SQLiteToolApprovalStore:
    """Persist human approval requests for agent-initiated tool actions."""

    def create(
        self,
        user_id: str,
        *,
        tool_name: str,
        arguments: dict[str, object],
        reason: str,
        source: str,
    ) -> ToolApprovalRequest:
        created_at = datetime.now(UTC).isoformat()
        approval = ToolApprovalRequest(
            approval_id=str(uuid4()),
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            source=source,
            status="pending",
            result=None,
            error_message=None,
            created_at=created_at,
            resolved_at=None,
        )
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tool_approval_requests
                (approval_id, user_id, tool_name, arguments_json, reason, source, status,
                 result_json, error_message, created_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.approval_id,
                    user_id,
                    approval.tool_name,
                    json.dumps(arguments),
                    approval.reason,
                    approval.source,
                    approval.status,
                    None,
                    None,
                    approval.created_at,
                    None,
                ),
            )
        return approval

    def list(
        self,
        user_id: str,
        *,
        status: ToolApprovalStatus | None = None,
    ) -> list[ToolApprovalRequest]:
        where_clause = "AND status = ?" if status else ""
        params = (user_id, status) if status else (user_id,)
        with database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT approval_id, tool_name, arguments_json, reason, source, status, result_json,
                       error_message, created_at, resolved_at
                FROM tool_approval_requests
                WHERE user_id = ?
                {where_clause}
                ORDER BY created_at DESC
                """,
                params,
            ).fetchall()
        return [self._approval_from_row(row) for row in rows]

    def get_pending(self, user_id: str, approval_id: str) -> ToolApprovalRequest | None:
        with database.connect() as connection:
            row = connection.execute(
                """
                SELECT approval_id, tool_name, arguments_json, reason, source, status, result_json,
                       error_message, created_at, resolved_at
                FROM tool_approval_requests
                WHERE user_id = ? AND approval_id = ? AND status = 'pending'
                """,
                (user_id, approval_id),
            ).fetchone()
        return self._approval_from_row(row) if row is not None else None

    def mark_executed(
        self,
        user_id: str,
        approval_id: str,
        *,
        result: dict[str, object],
    ) -> ToolApprovalRequest | None:
        return self._resolve(
            user_id,
            approval_id,
            status="executed",
            result_json=json.dumps(result),
            error_message=None,
        )

    def mark_rejected(self, user_id: str, approval_id: str) -> ToolApprovalRequest | None:
        return self._resolve(
            user_id,
            approval_id,
            status="rejected",
            result_json=None,
            error_message=None,
        )

    def mark_failed(
        self,
        user_id: str,
        approval_id: str,
        *,
        error_message: str,
    ) -> ToolApprovalRequest | None:
        return self._resolve(
            user_id,
            approval_id,
            status="failed",
            result_json=None,
            error_message=error_message,
        )

    def _resolve(
        self,
        user_id: str,
        approval_id: str,
        *,
        status: ToolApprovalStatus,
        result_json: str | None,
        error_message: str | None,
    ) -> ToolApprovalRequest | None:
        resolved_at = datetime.now(UTC).isoformat()
        with database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tool_approval_requests
                SET status = ?, result_json = ?, error_message = ?, resolved_at = ?
                WHERE user_id = ? AND approval_id = ? AND status = 'pending'
                """,
                (status, result_json, error_message, resolved_at, user_id, approval_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT approval_id, tool_name, arguments_json, reason, source, status, result_json,
                       error_message, created_at, resolved_at
                FROM tool_approval_requests
                WHERE user_id = ? AND approval_id = ?
                """,
                (user_id, approval_id),
            ).fetchone()
        return self._approval_from_row(row)

    @staticmethod
    def _approval_from_row(row) -> ToolApprovalRequest:
        return ToolApprovalRequest(
            approval_id=row["approval_id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments_json"]),
            reason=row["reason"],
            source=row["source"],
            status=row["status"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error_message=row["error_message"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )


tool_approval_store = SQLiteToolApprovalStore()
