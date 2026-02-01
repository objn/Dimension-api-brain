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

    inspector = inspect(engine)

    code = []
    code.append('"""')
    code.append('Auto-generated SQLAlchemy models from database schema.')
    code.append('Generated similar to TypeORM entity generation.')
    code.append('"""')
    code.append('from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Boolean, Float, JSON, ARRAY')
    code.append('from sqlalchemy.dialects.postgresql import UUID, BYTEA, INET')
    code.append('from sqlalchemy.orm import relationship')
    code.append('from datetime import datetime')
    code.append('import uuid')
    code.append('')
    code.append('from .connection import Base')
    code.append('')
    code.append('')

    # Generate a model for each table
    for table_name in sorted(metadata.tables.keys()):
        table = metadata.tables[table_name]
        class_name = snake_to_pascal(table_name)

        code.append(f'class {class_name}(Base):')
        code.append(f'    """Model for {table_name} table"""')
        code.append(f'    __tablename__ = "{table_name}"')
        code.append('')

        # Get primary keys
        pk_columns = [col.name for col in table.primary_key.columns]

        # Generate columns
        for column in table.columns:
            col_def = generate_column_definition(column, pk_columns)
            code.append(f'    {col_def}')

        code.append('')

        # Get foreign keys and generate relationships
        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            rel_def = generate_relationship(fk, table_name)
            if rel_def:
                code.append(f'    {rel_def}')

        code.append('')
        code.append('')

    return '\n'.join(code)


def generate_column_definition(column, pk_columns: list) -> str:
    """Generate SQLAlchemy column definition"""
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
        'DATE': 'DateTime',
        'FLOAT': 'Float',
        'DOUBLE': 'Float',
        'NUMERIC': 'Float',
        'JSON': 'JSON',
        'JSONB': 'JSON',
        'BYTEA': 'BYTEA',
        'INET': 'INET',
    }

    # Get the base type name
    base_type = col_type.split('(')[0].upper()
    python_type = type_mapping.get(base_type, col_type)

    # Build column definition
    parts = [f'{col_name} = Column({python_type}']

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


def generate_relationship(fk: dict, table_name: str) -> str:
    """Generate SQLAlchemy relationship definition"""
    if not fk.get('constrained_columns') or not fk.get('referred_table'):
        return None

    referred_table = fk['referred_table']
    referred_class = snake_to_pascal(referred_table)
    constrained_col = fk['constrained_columns'][0]

    # Create relationship name (remove _id suffix if present)
    rel_name = constrained_col.replace('_id', '')
    if rel_name == constrained_col:
        rel_name = referred_table

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
