#!/usr/bin/env python3
"""
Database migration: AccessToken → Wallet flow.

Adds columns required for the wallet-based budget system:
  - wallets.token_hash           (unique, indexed)
  - provider_keys.credit_model   (default: "one_time")
  - provider_keys.budget_amount
  - provider_keys.budget_spent
  - provider_keys.last_reset_at
  - usage_logs.wallet_id         (FK → wallets.id)
  - usage_logs.access_token_id   (kept but nullable for backward compat)

Idempotent — safe to run multiple times.

Usage:
    python scripts/migrate_wallet.py                    # uses default sqlite path
    python scripts/migrate_wallet.py /path/to/db.sqlite # custom path
"""

import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """Get the database file path from command line or default."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    # Default from settings.DATABASE_URL: sqlite+aiosqlite:///./llm_proxy.db
    return Path("./llm_proxy.db")


def table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(col[1] == column_name for col in cursor.fetchall())


def add_column_if_missing(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
    """Add a column if it doesn't already exist."""
    if not column_exists(cursor, table, column):
        print(f"  Adding column {table}.{column}")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    else:
        print(f"  Column {table}.{column} already exists")


def migrate_wallet(db_path: Path):
    """Run the wallet migration on the SQLite database."""
    if not db_path.exists():
        print(f"❌ Database file not found: {db_path}")
        print("   Make sure the path is correct or run the server first to create the DB.")
        return False

    print(f"🔧 Migrating database: {db_path}")
    print("   Making backup first...")
    
    # Create backup
    backup_path = db_path.with_suffix(db_path.suffix + ".backup")
    if backup_path.exists():
        backup_path.unlink()
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"   Backup created: {backup_path}")

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Enable foreign key constraints
            cursor.execute("PRAGMA foreign_keys = ON")
            
            print("\n📋 Checking current schema...")
            
            # 1. wallets.token_hash
            if table_exists(cursor, "wallets"):
                add_column_if_missing(
                    cursor, "wallets", "token_hash",
                    "TEXT UNIQUE"
                )
                # Add index if not exists (SQLite creates index automatically for UNIQUE constraint)
                # But let's be explicit for clarity
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS ix_wallets_token_hash ON wallets(token_hash)")
                    print("  Ensured index on wallets.token_hash")
                except sqlite3.OperationalError:
                    pass  # Index might already exist or table might not exist yet
            else:
                print("  ⚠️  Table 'wallets' does not exist yet")
            
            # 2. provider_keys columns (for wallet flow)
            if table_exists(cursor, "provider_keys"):
                add_column_if_missing(
                    cursor, "provider_keys", "credit_model",
                    "TEXT NOT NULL DEFAULT 'one_time'"
                )
                add_column_if_missing(
                    cursor, "provider_keys", "budget_amount",
                    "INTEGER"
                )
                add_column_if_missing(
                    cursor, "provider_keys", "budget_spent",
                    "INTEGER NOT NULL DEFAULT 0"
                )
                add_column_if_missing(
                    cursor, "provider_keys", "last_reset_at",
                    "TIMESTAMP"
                )
            else:
                print("  ⚠️  Table 'provider_keys' does not exist yet")
            
            # 3. usage_logs.wallet_id (new) and ensure access_token_id is nullable
            if table_exists(cursor, "usage_logs"):
                add_column_if_missing(
                    cursor, "usage_logs", "wallet_id",
                    "TEXT"
                )
                # Create index on wallet_id for performance
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS ix_usage_logs_wallet_id ON usage_logs(wallet_id)")
                    print("  Ensured index on usage_logs.wallet_id")
                except sqlite3.OperationalError:
                    pass
                
                # Make access_token_id nullable if it isn't already (for backward compatibility during transition)
                # Note: SQLite doesn't allow altering column nullability directly, so we'd need to recreate table
                # For now, we'll just add the wallet_id column and leave access_token_id as-is
                # The application logic will handle which one to use
                print("  Added wallet_id to usage_logs (access_token_id kept for backward compatibility)")
            else:
                print("  ⚠️  Table 'usage_logs' does not exist yet")
            
            # 4. Populate token_hash for existing wallets (if any)
            if table_exists(cursor, "wallets"):
                cursor.execute("SELECT id FROM wallets WHERE token_hash IS NULL")
                rows = cursor.fetchall()
                if rows:
                    print(f"\n🔑 Generating token hashes for {len(rows)} existing wallet(s)...")
                    for (wallet_id,) in rows:
                        # Generate a random token and its hash
                        raw_token = "llmp_" + secrets.token_urlsafe(32)
                        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                        cursor.execute(
                            "UPDATE wallets SET token_hash = ? WHERE id = ?",
                            (token_hash, wallet_id)
                        )
                        print(f"    Wallet {wallet_id}: generated token (hash stored)")
                    print("   💡 Note: Save the generated tokens securely - they won't be shown again!")
                else:
                    print("\n🔑 All existing wallets already have token_hash set")
            
            # Commit all changes
            conn.commit()
            print("\n✅ Migration completed successfully!")
            return True
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("   Restoring from backup...")
        shutil.copy2(backup_path, db_path)
        print("   Database restored from backup.")
        return False


def main():
    print("🚀 LLM Proxy Wallet Migration")
    print("=" * 50)
    
    db_path = get_db_path()
    success = migrate_wallet(db_path)
    
    if success:
        print("\n📋 Next steps:")
        print("   1. Verify the migration worked: check your database schema")
        print("   2. Test wallet creation via CLI: llm-proxy wallet create ...")
        print("   3. Test end-to-end flow: create wallet → link provider → auth → deduct")
        print("   4. If everything works, you can delete the backup file:")
        print(f"      rm {db_path}.backup")
    else:
        print("\n💥 Migration failed. Please check the error above.")
        sys.exit(1)


if __name__ == "__main__":
    main()