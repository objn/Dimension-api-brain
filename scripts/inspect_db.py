"""
Script to inspect database schema and generate model information.
Run this to see what tables and columns exist in your database.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect
from src.database import engine
from src.config import settings


def inspect_database():
    """Inspect database and print schema information"""
    inspector = inspect(engine)

    print(f"\n{'='*80}")
    print(f"DATABASE: {settings.database_url.split('@')[-1]}")  # Hide credentials
    print(f"{'='*80}\n")

    # Get all table names
    tables = inspector.get_table_names()
    print(f"Found {len(tables)} tables:\n")

    for table_name in sorted(tables):
        print(f"\n[TABLE] {table_name}")
        print("-" * 80)

        # Get columns
        columns = inspector.get_columns(table_name)
        print("\nColumns:")
        for col in columns:
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            col_type = str(col['type'])
            default = f" DEFAULT {col.get('default', '')}" if col.get('default') else ""
            print(f"  - {col['name']:30} {col_type:20} {nullable:10}{default}")

        # Get primary keys
        pk = inspector.get_pk_constraint(table_name)
        if pk and pk['constrained_columns']:
            print(f"\nPrimary Key: {', '.join(pk['constrained_columns'])}")

        # Get foreign keys
        fks = inspector.get_foreign_keys(table_name)
        if fks:
            print("\nForeign Keys:")
            for fk in fks:
                print(f"  - {', '.join(fk['constrained_columns'])} -> {fk['referred_table']}.{', '.join(fk['referred_columns'])}")

        # Get indexes
        indexes = inspector.get_indexes(table_name)
        if indexes:
            print("\nIndexes:")
            for idx in indexes:
                unique = "UNIQUE" if idx['unique'] else ""
                print(f"  - {idx['name']}: {', '.join(idx['column_names'])} {unique}")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    try:
        inspect_database()
    except Exception as e:
        print(f"\n[ERROR] Error connecting to database: {e}")
        print(f"\nConnection string (without password): {settings.database_url.split(':')[0]}://...@{settings.database_url.split('@')[-1]}")
        sys.exit(1)
