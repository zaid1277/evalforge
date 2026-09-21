from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Import the app's settings and the SQLAlchemy declarative Base, plus every
# model module (so each model registers itself on Base.metadata -- same
# pattern as the noqa imports in app/main.py). This is what lets
# `alembic revision --autogenerate` compare the real ORM models against
# the database.
from app.config import settings
from app.db.database import Base
from app.models import chunk as _chunk_model  # noqa: F401
from app.models import evaluation_case as _evaluation_case_model  # noqa: F401
from app.models import evaluation_case_source as _evaluation_case_source_model  # noqa: F401
from app.models import evaluation_result as _evaluation_result_model  # noqa: F401
from app.models import evaluation_run as _evaluation_run_model  # noqa: F401
from app.models import project as _project_model  # noqa: F401
from app.models import source as _source_model  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The same DATABASE_URL the FastAPI app itself uses (from app/config.py,
# which reads api/.env) -- not duplicated in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
