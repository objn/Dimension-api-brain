"""
Auto-generate SQLAlchemy models from existing database schema.
Similar to TypeORM's entity generation.

Usage:
    python scripts/generate_models.py
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, MetaData, inspect
from sqlalchemy.ext.automap import automap_base
from src.config import settings

# Custom class name overrides: {table_name: ClassName}
# Use this to keep backward-compatible class names
CLASS_NAME_OVERRIDES = {
    "Jobs": "Job",
    "JobResults": "JobResults",
    "JobTypes": "Jobtypes",
}

# Column names that conflict with SQLAlchemy reserved attributes
RESERVED_COLUMN_RENAMES = {
    "metadata": "metadata_json",
}


def generate_models_from_db():
    """
    Generate SQLAlchemy models from existing database schema.
    Similar to TypeORM's automatic entity generation.
    """
    print(f"\n{'='*80}")
    print("Generating SQLAlchemy Models from Database Schema")
    print(f"{'='*80}\n")

    try:
        # Create engine
        engine = create_engine(settings.database_url)

        # Register pgvector type before reflecting
        try:
            from pgvector.sqlalchemy import Vector
            print("pgvector extension loaded")
        except ImportError:
            print("[WARN] pgvector not installed, Vector columns will use raw type")

        # Create metadata and reflect all tables
        metadata = MetaData()
        metadata.reflect(bind=engine)

        print(f"Connected to: {settings.database_url.split('@')[-1]}")
        print(f"Found {len(metadata.tables)} tables\n")

        # Generate model code
        model_code = generate_model_code(metadata, engine)

        # Write to file
        output_file = Path(__file__).parent.parent / "src" / "database" / "models.py"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(model_code)

        print(f"\n{'='*80}")
        print(f"✓ Models generated successfully!")
        print(f"  Output: {output_file}")
        print(f"{'='*80}\n")

        # Also create automap version
        create_automap_models()

    except Exception as e:
        print(f"\n[ERROR] Failed to generate models: {e}")
        sys.exit(1)


def generate_model_code(metadata: MetaData, engine) -> str:
    """Generate Python code for SQLAlchemy models"""
    from sqlalchemy import text, types as sa_types

    inspector = inspect(engine)

    # -------------------------------------------------------------------------
    # 1. Query raw column types from information_schema
    #    This catches types that SQLAlchemy's reflect doesn't recognize (e.g. vector)
    # -------------------------------------------------------------------------
    raw_col_types = {}  # {(table_name, col_name): (udt_name, type_modifier)}
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT c.table_name, c.column_name, c.udt_name,
                       COALESCE(c.character_maximum_length, c.numeric_precision) as type_param,
                       CASE
                           WHEN c.udt_name = 'vector' THEN
                               (SELECT atttypmod FROM pg_attribute a
                                JOIN pg_class cl ON a.attrelid = cl.oid
                                JOIN pg_namespace ns ON cl.relnamespace = ns.oid
                                WHERE cl.relname = c.table_name
                                AND a.attname = c.column_name
                                AND ns.nspname = c.table_schema)
                           ELSE NULL
                       END as vector_dim
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
            """))
            for row in result:
                raw_col_types[(row[0], row[1])] = {
                    'udt_name': row[2],
                    'type_param': row[3],
                    'vector_dim': row[4],
                }
    except Exception as e:
        print(f"[WARN] Could not query raw column types: {e}")

    # -------------------------------------------------------------------------
    # 2. Pre-build FK lookup & detect polymorphic FK columns
    #    Polymorphic FK = one column with FK constraints to multiple tables
    # -------------------------------------------------------------------------
    fk_lookup = {}           # {table: {col: 'ref_table.ref_col'}}
    polymorphic_fk = set()   # {(table, col)} - columns to skip FK/relationships for

    for table_name in metadata.tables:
        fks = inspector.get_foreign_keys(table_name)
        fk_lookup[table_name] = {}
        col_targets = {}  # {col: set(referred_tables)}

        for fk in fks:
            if fk.get('constrained_columns') and fk.get('referred_table') and fk.get('referred_columns'):
                for c_col, r_col in zip(fk['constrained_columns'], fk['referred_columns']):
                    col_targets.setdefault(c_col, set()).add(fk['referred_table'])
                    fk_lookup[table_name][c_col] = f"{fk['referred_table']}.{r_col}"

        # Mark columns with FKs to multiple tables as polymorphic
        for col, tables in col_targets.items():
            if len(tables) > 1:
                polymorphic_fk.add((table_name, col))
                fk_lookup[table_name].pop(col, None)  # Don't add ForeignKey
                print(f"  [INFO] Skipping polymorphic FK: {table_name}.{col} -> {tables}")

    # -------------------------------------------------------------------------
    # 3. Detect vector columns from raw types
    # -------------------------------------------------------------------------
    has_vector = any(
        info['udt_name'] == 'vector'
        for info in raw_col_types.values()
    )

    # -------------------------------------------------------------------------
    # 4. Generate code
    # -------------------------------------------------------------------------
    code = []
    code.append('"""')
    code.append('Auto-generated SQLAlchemy models from database schema.')
    code.append('Generated similar to TypeORM entity generation.')
    code.append('"""')
    code.append('from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Boolean, Float, JSON, ARRAY')
    code.append('from sqlalchemy.dialects.postgresql import UUID, BYTEA, INET')
    code.append('from sqlalchemy.orm import relationship')
    if has_vector:
        code.append('from pgvector.sqlalchemy import Vector')
    code.append('from datetime import datetime')
    code.append('import uuid')
    code.append('')
    code.append('from .connection import Base')
    code.append('')
    code.append('')

    # Generate a model for each table
    for table_name in sorted(metadata.tables.keys()):
        table = metadata.tables[table_name]
        class_name = CLASS_NAME_OVERRIDES.get(table_name, snake_to_pascal(table_name))
        table_fks = fk_lookup.get(table_name, {})

        code.append(f'class {class_name}(Base):')
        code.append(f'    """Model for {table_name} table"""')
        code.append(f'    __tablename__ = "{table_name}"')
        code.append('')

        # Get primary keys
        pk_columns = [col.name for col in table.primary_key.columns]

        # Generate columns
        for column in table.columns:
            fk_target = table_fks.get(column.name)
            raw_info = raw_col_types.get((table_name, column.name))
            col_def = generate_column_definition(column, pk_columns, fk_target, raw_info)
            code.append(f'    {col_def}')

        code.append('')

        # Get foreign keys and generate relationships (with unique names)
        # Skip relationships for polymorphic FK columns
        fks = inspector.get_foreign_keys(table_name)
        used_rel_names = set()
        for fk in fks:
            # Check if this FK's column is polymorphic
            constrained_cols = fk.get('constrained_columns', [])
            if constrained_cols and (table_name, constrained_cols[0]) in polymorphic_fk:
                continue  # Skip polymorphic FK relationships
            rel_def = generate_relationship(fk, table_name, used_rel_names)
            if rel_def:
                code.append(f'    {rel_def}')

        code.append('')
        code.append('')

    return '\n'.join(code)


def generate_column_definition(column, pk_columns: list, fk_target: str = None, raw_type_info: dict = None) -> str:
    """Generate SQLAlchemy column definition"""
    from sqlalchemy import types as sa_types

    col_name = column.name
    col_type = str(column.type)

    # Map SQLAlchemy types to Python types
    type_mapping = {
        'UUID': 'UUID(as_uuid=True)',
        'VARCHAR': f'String({column.type.length})' if hasattr(column.type, 'length') and column.type.length else 'String',
        'TEXT': 'Text',
        'INTEGER': 'Integer',
        'BIGINT': 'Integer',
        'SMALLINT': 'Integer',
        'BOOLEAN': 'Boolean',
        'TIMESTAMP': 'DateTime',
        'TIMESTAMP WITHOUT TIME ZONE': 'DateTime',
        'TIMESTAMP WITH TIME ZONE': 'DateTime',
        'DATE': 'DateTime',
        'FLOAT': 'Float',
        'FLOAT4': 'Float',
        'FLOAT8': 'Float',
        'DOUBLE': 'Float',
        'DOUBLE PRECISION': 'Float',
        'DOUBLE_PRECISION': 'Float',
        'NUMERIC': 'Float',
        'JSON': 'JSON',
        'JSONB': 'JSON',
        'BYTEA': 'BYTEA',
        'INET': 'INET',
    }

    # PostgreSQL udt_name -> Python type (fallback for NullType)
    udt_type_mapping = {
        'uuid': 'UUID(as_uuid=True)',
        'varchar': f'String({column.type.length})' if hasattr(column.type, 'length') and column.type.length else 'String',
        'text': 'Text',
        'int4': 'Integer',
        'int8': 'Integer',
        'int2': 'Integer',
        'bool': 'Boolean',
        'timestamp': 'DateTime',
        'timestamptz': 'DateTime',
        'date': 'DateTime',
        'float4': 'Float',
        'float8': 'Float',
        'numeric': 'Float',
        'json': 'JSON',
        'jsonb': 'JSON',
        'bytea': 'BYTEA',
        'inet': 'INET',
    }

    python_type = None

    # ---- Handle pgvector Vector type (both NullType and recognized) ----
    is_vector_str = 'VECTOR' in col_type.upper()
    is_null_vector = (
        isinstance(column.type, sa_types.NullType)
        and raw_type_info
        and raw_type_info.get('udt_name') == 'vector'
    )

    if is_vector_str or is_null_vector:
        import re
        # Try to extract dimension from type string first (e.g. "VECTOR(1536)")
        match = re.search(r'\((\d+)\)', col_type)
        if match:
            python_type = f'Vector({match.group(1)})'
        elif raw_type_info and raw_type_info.get('vector_dim'):
            dim = int(raw_type_info['vector_dim'])
            python_type = f'Vector({dim})' if dim > 0 else 'Vector'
        else:
            python_type = 'Vector'

    # ---- Handle other NullType (type not recognized by SQLAlchemy reflection) ----
    elif isinstance(column.type, sa_types.NullType) and raw_type_info:
        udt_name = raw_type_info.get('udt_name', '')
        python_type = udt_type_mapping.get(udt_name, f'Text  # unknown udt: {udt_name}')

    # ---- Normal type mapping ----
    if python_type is None:
        base_type = col_type.split('(')[0].upper().strip()
        python_type = type_mapping.get(base_type, None)
        if python_type is None:
            # Try with full type string (e.g. DOUBLE PRECISION)
            python_type = type_mapping.get(col_type.upper().strip(), None)
        if python_type is None:
            # Last resort: check raw type info
            if raw_type_info:
                udt_name = raw_type_info.get('udt_name', '')
                python_type = udt_type_mapping.get(udt_name, col_type)
            else:
                python_type = col_type

    # Build column definition
    # Handle reserved column names
    python_name = RESERVED_COLUMN_RENAMES.get(col_name, col_name)
    if python_name != col_name:
        # Map Python attribute to actual DB column name
        parts = [f'{python_name} = Column("{col_name}", {python_type}']
    else:
        parts = [f'{col_name} = Column({python_type}']

    # Add ForeignKey if this column has one
    if fk_target:
        parts.append(f"ForeignKey('{fk_target}')")

    # Add primary key
    if col_name in pk_columns:
        parts.append('primary_key=True')

    # Add nullable
    if not column.nullable and col_name not in pk_columns:
        parts.append('nullable=False')

    # Add default
    if column.default is not None:
        default_val = column.default.arg
        if callable(default_val):
            if 'uuid' in str(default_val).lower():
                parts.append('default=uuid.uuid4')
            elif 'now' in str(default_val).lower() or 'current' in str(default_val).lower():
                parts.append('default=datetime.utcnow')
        else:
            parts.append(f'default={repr(default_val)}')

    return ', '.join(parts) + ')'


def generate_relationship(fk: dict, table_name: str, used_names: set) -> str:
    """Generate SQLAlchemy relationship definition with unique names"""
    if not fk.get('constrained_columns') or not fk.get('referred_table'):
        return None

    referred_table = fk['referred_table']
    referred_class = CLASS_NAME_OVERRIDES.get(referred_table, snake_to_pascal(referred_table))
    constrained_col = fk['constrained_columns'][0]

    # Create relationship name (remove _id suffix if present)
    rel_name = constrained_col.replace('_id', '')
    if rel_name == constrained_col:
        rel_name = referred_table

    # Ensure unique relationship name within the class
    original_name = rel_name
    suffix = 2
    while rel_name in used_names:
        rel_name = f"{original_name}_{suffix}"
        suffix += 1
    used_names.add(rel_name)

    return f'{rel_name} = relationship("{referred_class}", foreign_keys=[{constrained_col}])'


def snake_to_pascal(snake_str: str) -> str:
    """Convert snake_case to PascalCase"""
    components = snake_str.split('_')
    return ''.join(x.title() for x in components)


def create_automap_models():
    """
    Create automap models that automatically map to database tables.
    This is similar to TypeORM's automatic entity loading.
    """
    output_file = Path(__file__).parent.parent / "src" / "database" / "automap.py"

    code = [
        '"""',
        'Automap models - Automatically reflect database schema.',
        'Similar to TypeORM\'s automatic entity discovery.',
        '',
        'Usage:',
        '    from src.database.automap import Base, User, Post, etc.',
        '"""',
        'from sqlalchemy import create_engine, MetaData',
        'from sqlalchemy.ext.automap import automap_base',
        'from sqlalchemy.orm import Session',
        '',
        'from src.config import settings',
        '',
        '# Create engine',
        'engine = create_engine(settings.database_url)',
        '',
        '# Reflect the database schema',
        'Base = automap_base()',
        'Base.prepare(autoload_with=engine)',
        '',
        '# Access tables as classes (like TypeORM entities)',
        '# Example: User = Base.classes.users',
        '# Example: Post = Base.classes.posts',
        '',
        '# You can access all tables through Base.classes',
        '# For example:',
        '# from src.database.automap import Base',
        '# User = Base.classes.users',
        '',
    ]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write('\n'.join(code))

    print(f"✓ Automap models created: {output_file}")


if __name__ == "__main__":
    generate_models_from_db()
