import sqlite3
import pytest
from pathlib import Path
from src.storage.database import DatabaseManager
from src.storage.maintenance import DatabaseMaintenanceDaemon

def test_maintenance_daemon_on_isolated_db(tmp_path: Path):
    db_file = tmp_path / "maint_test.db"
    
    db_mgr = DatabaseManager(db_path=str(db_file))
    
    # 1. Quick check
    daemon = DatabaseMaintenanceDaemon(db=db_mgr)
    is_ok, detail = daemon.check_integrity()
    assert is_ok is True
    assert detail == "ok"
    
    # 2. WAL checkpoint
    res_wal = daemon.run_wal_checkpoint(mode="PASSIVE")
    assert res_wal["busy"] is False
    
    # 3. Incremental vacuum
    res_vac = daemon.run_incremental_vacuum(pages=100)
    assert res_vac["status"] == "COMPLETED"
    
    # 4. Optimize query planner
    res_opt = daemon.run_query_planner_optimize()
    assert res_opt["status"] == "COMPLETED"
    
    # 5. Full cycle
    res_cycle = daemon.run_full_maintenance_cycle()
    assert res_cycle["status"] == "SUCCESS"
    assert res_cycle["integrity_ok"] is True
