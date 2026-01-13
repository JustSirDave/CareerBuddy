#!/usr/bin/env python3
"""
Database backup script
Backs up PostgreSQL database to local storage
Can be scheduled with cron or run manually
"""
import subprocess
import os
from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from loguru import logger


def backup_database():
    """
    Create a PostgreSQL database backup using pg_dump
    """
    try:
        # Create backups directory
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"buddy_backup_{timestamp}.sql"
        
        logger.info(f"[BACKUP] Starting database backup to {backup_file}")
        
        # Extract database connection details
        db_url = settings.database_url
        
        # For Docker setup, use docker-compose exec
        if os.getenv("USE_DOCKER", "true").lower() == "true":
            cmd = [
                "docker-compose", "exec", "-T", "postgres",
                "pg_dump", "-U", "postgres", "-d", "buddy"
            ]
        else:
            # For local PostgreSQL
            cmd = [
                "pg_dump",
                "-h", "localhost",
                "-p", "5432",
                "-U", "postgres",
                "-d", "buddy",
                "-F", "p",  # Plain text format
                "-f", str(backup_file)
            ]
        
        # Run backup command
        with open(backup_file, "w") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300  # 5 minute timeout
            )
        
        if result.returncode == 0:
            # Get file size
            size_mb = backup_file.stat().st_size / (1024 * 1024)
            logger.info(f"[BACKUP] ✅ Backup successful: {backup_file} ({size_mb:.2f} MB)")
            
            # Clean up old backups (keep last 7 days)
            cleanup_old_backups(backup_dir, days_to_keep=7)
            
            return True, str(backup_file)
        else:
            error_msg = result.stderr
            logger.error(f"[BACKUP] ❌ Backup failed: {error_msg}")
            return False, error_msg
    
    except subprocess.TimeoutExpired:
        logger.error("[BACKUP] ❌ Backup timed out after 5 minutes")
        return False, "Backup timed out"
    
    except Exception as e:
        logger.error(f"[BACKUP] ❌ Backup failed: {e}")
        return False, str(e)


def cleanup_old_backups(backup_dir: Path, days_to_keep: int = 7):
    """
    Remove backup files older than specified days
    
    Args:
        backup_dir: Directory containing backups
        days_to_keep: Number of days to keep backups
    """
    try:
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(days=days_to_keep)
        
        removed_count = 0
        for backup_file in backup_dir.glob("buddy_backup_*.sql"):
            if backup_file.stat().st_mtime < cutoff_time.timestamp():
                backup_file.unlink()
                removed_count += 1
                logger.info(f"[BACKUP] Removed old backup: {backup_file.name}")
        
        if removed_count > 0:
            logger.info(f"[BACKUP] Cleaned up {removed_count} old backup(s)")
    
    except Exception as e:
        logger.error(f"[BACKUP] Error cleaning up old backups: {e}")


def restore_database(backup_file: str):
    """
    Restore database from a backup file
    
    Args:
        backup_file: Path to backup SQL file
    
    WARNING: This will drop and recreate the database!
    """
    try:
        backup_path = Path(backup_file)
        if not backup_path.exists():
            logger.error(f"[RESTORE] Backup file not found: {backup_file}")
            return False, "Backup file not found"
        
        logger.warning(f"[RESTORE] Starting database restore from {backup_file}")
        logger.warning("[RESTORE] ⚠️  This will overwrite the current database!")
        
        # For Docker setup
        if os.getenv("USE_DOCKER", "true").lower() == "true":
            cmd = [
                "docker-compose", "exec", "-T", "postgres",
                "psql", "-U", "postgres", "-d", "buddy"
            ]
        else:
            cmd = [
                "psql",
                "-h", "localhost",
                "-p", "5432",
                "-U", "postgres",
                "-d", "buddy"
            ]
        
        # Run restore command
        with open(backup_path, "r") as f:
            result = subprocess.run(
                cmd,
                stdin=f,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300
            )
        
        if result.returncode == 0:
            logger.info(f"[RESTORE] ✅ Database restored from {backup_file}")
            return True, "Database restored successfully"
        else:
            error_msg = result.stderr
            logger.error(f"[RESTORE] ❌ Restore failed: {error_msg}")
            return False, error_msg
    
    except Exception as e:
        logger.error(f"[RESTORE] ❌ Restore failed: {e}")
        return False, str(e)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        if len(sys.argv) < 3:
            print("Usage: python backup_database.py restore <backup_file>")
            sys.exit(1)
        
        backup_file = sys.argv[2]
        success, message = restore_database(backup_file)
        print(message)
        sys.exit(0 if success else 1)
    else:
        # Run backup
        success, message = backup_database()
        print(message)
        sys.exit(0 if success else 1)
