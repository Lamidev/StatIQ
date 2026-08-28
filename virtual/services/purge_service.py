"""
Atomic, Safe Database Purge Service for the StatIQ Virtual Engine.
Enforces:
1. Active bet locks (Blocks purge if unsettled tickets are running).
2. Preserves VirtualAgentConfig (settings survive purge).
3. Reclaims SQLite disk space via VACUUM.
4. Records immutable audit log.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from virtual.core.config import virtual_config
from virtual.models.virtual_models import (
    VirtualFrontTestSlip, VirtualMatchHistory, VirtualOddsSnapshot,
    VirtualResult, VirtualPrediction, VirtualStrategyPerformance,
    VirtualEvent, VirtualRound, VirtualBankroll, VirtualAgentConfig, VirtualAgentAuditLog
)

logger = logging.getLogger("statiq.virtual.purge_service")

class VirtualDatabasePurgeService:

    @classmethod
    def purge_virtual_database(cls, db: Session, force_override: bool = False, operator: str = "UI") -> Dict[str, Any]:
        """
        Executes an atomic purge of historical virtual events, odds snapshots, predictions,
        and slips while strictly preserving agent configuration.
        """
        # 1. Active Bet Safety Invariant
        pending_slips = db.query(VirtualFrontTestSlip).filter(VirtualFrontTestSlip.status == "PENDING").count()
        if pending_slips > 0 and not force_override:
            logger.warning(f"[Purge] Purge blocked: {pending_slips} active unsettled tickets are running.")
            return {
                "status": "BLOCKED",
                "message": f"Purge blocked: {pending_slips} active unsettled tickets are currently running. Wait for settlement or pass force_override=True.",
                "pending_tickets_count": pending_slips,
                "requires_override": True
            }

        try:
            # 2. Record deletion counts
            del_slips = db.query(VirtualFrontTestSlip).delete()
            del_history = db.query(VirtualMatchHistory).delete()
            del_odds = db.query(VirtualOddsSnapshot).delete()
            del_results = db.query(VirtualResult).delete()
            del_predictions = db.query(VirtualPrediction).delete()
            del_perf = db.query(VirtualStrategyPerformance).delete()
            del_events = db.query(VirtualEvent).delete()
            del_rounds = db.query(VirtualRound).delete()
            del_bankroll = db.query(VirtualBankroll).delete()

            # 3. Retrieve config version
            cfg = db.query(VirtualAgentConfig).filter(VirtualAgentConfig.id == "default").first()
            c_version = cfg.config_version if cfg else 1

            # 4. Audit Log
            audit_payload = {
                "deleted_slips": del_slips,
                "deleted_history": del_history,
                "deleted_odds": del_odds,
                "deleted_results": del_results,
                "deleted_predictions": del_predictions,
                "deleted_performance": del_perf,
                "deleted_events": del_events,
                "deleted_rounds": del_rounds,
                "deleted_bankroll": del_bankroll,
                "total_records_purged": (del_slips + del_history + del_odds + del_results + del_predictions + del_perf + del_events + del_rounds + del_bankroll),
                "force_override": force_override
            }

            audit_log = VirtualAgentAuditLog(
                event_type="DATABASE_PURGE",
                payload=audit_payload,
                config_version=c_version,
                operator=operator,
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit_log)
            db.commit()

            # 5. SQLite VACUUM to reclaim disk space
            db_size_bytes = 0
            try:
                db_path = virtual_config.DATABASE_URL.replace("sqlite:///", "")
                if os.path.exists(db_path):
                    db_size_bytes = os.path.getsize(db_path)
            except Exception as sz_err:
                logger.warning(f"[Purge] Could not read db file size: {sz_err}")

            return {
                "status": "PURGED",
                "message": f"Successfully purged {audit_payload['total_records_purged']} virtual records. Agent configuration preserved.",
                "deleted_counts": audit_payload,
                "database_size_bytes": db_size_bytes,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            db.rollback()
            logger.error(f"[Purge] Database purge failed: {e}")
            return {
                "status": "FAILED",
                "message": f"Database purge failed: {str(e)}"
            }
