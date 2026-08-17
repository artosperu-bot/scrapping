from __future__ import annotations

from .audit_events import AuditEvent


class AuditLiveUiMixin:
    """Final structured-audit/error-recovery bridge for live UI events."""

    def _active_snapshot_for(self, process_type: str):
        wanted = str(process_type or "").upper()
        for snapshot in list(getattr(self, "_active_snapshots", {}).values()):
            if str(getattr(snapshot, "process_type", "")).upper() == wanted:
                return snapshot
        return None

    def _record_live_audit(
        self,
        process_type: str,
        *,
        run_id: str | None = None,
        product_id: str = "",
        stage: str = "",
        source: str = "",
        url: str = "",
        status: str = "PROGRESS",
        detail: str = "",
        result: str = "",
    ) -> None:
        sink = self.__dict__.get("audit_sink")
        if sink is None:
            return
        process = str(process_type or "").upper()
        snapshot = self._active_snapshot_for(process)
        effective_run = str(run_id or getattr(snapshot, "run_id", "") or f"{process.lower()}-live")
        sink.emit(
            AuditEvent.create(
                effective_run,
                process,
                product_id=product_id,
                stage=stage,
                source=source,
                url=url,
                status=status,
                detail=detail,
                result=result,
            )
        )

    def _excel_progress_log(self, message):
        result = super()._excel_progress_log(message)
        text = str(message or "")
        stage = self._excel_stage_from_log(text) or "PROGRESS"
        low = text.lower()
        status = "REJECTED" if ("rejected" in low or "evidence_allowed=no" in low or "source_rejected=" in low) else "PROGRESS"
        source = "PDF" if stage == "PDF" else "WEB" if stage in {"SEARCH", "VALIDATE", "EXTRACT"} else ""
        self._record_live_audit("EXCEL", stage=stage, source=source, status=status, detail=text[:1000])
        return result

    def _apply_pdf_live_event(self, index: int, event: dict):
        kind = str(event.get("type") or "")
        url = str(event.get("url") or "")
        if kind not in {"log", "final_result"}:
            status = (
                "ERROR" if kind == "error" or event.get("error") else
                "REJECTED" if kind == "rejected" else
                "FOUND" if kind == "validated" else
                "PROGRESS"
            )
            product_id = ""
            try:
                identity = self._identity_for_index(index)
                if identity is not None:
                    product_id = str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "")
            except Exception:
                product_id = str(index + 1)
            self._record_live_audit(
                "PDF",
                run_id=f"pdf-review-{index}",
                product_id=product_id,
                stage=str(event.get("stage") or kind).upper(),
                source="PDF",
                url=url,
                status=status,
                detail=str(event.get("reason") or event.get("status") or event.get("error") or kind),
            )
        return super()._apply_pdf_live_event(index, event)

    def _recover_live_controls(self, module: str, error: str) -> None:
        kind = str(module or "").upper()
        text = str(error or "Error")
        if kind == "PRICE":
            self._price_running = False
            for name in ("price_selected_btn", "price_all_btn"):
                button = self.__dict__.get(name)
                if button is not None:
                    button.configure(state="normal")
            status = self.__dict__.get("price_status")
            if status is not None:
                status.set(f"ERROR · {text}")
        elif kind == "MEDIA":
            self._media_running = False
            for name in ("media_selected_btn", "media_all_btn"):
                button = self.__dict__.get(name)
                if button is not None:
                    button.configure(state="normal")
            status = self.__dict__.get("media_status")
            if status is not None:
                status.set(f"ERROR · {text}")
        elif kind == "SOCIAL_VIDEO":
            self._social_video_running = False
            button = self.__dict__.get("social_video_btn")
            if button is not None:
                button.configure(state="normal")
            status = self.__dict__.get("social_video_status")
            if status is not None:
                status.set(f"ERROR · {text}")
        elif kind == "EXCEL":
            button = self.__dict__.get("runbtn")
            if button is not None:
                button.configure(state="normal")
            status = self.__dict__.get("excel_progress_status")
            if status is not None:
                status.set(f"ERROR · {text}")
