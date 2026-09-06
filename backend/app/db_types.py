"""Database type helpers.

PostgreSQL JSONB is used in production, but JSONB is not available on SQLite.
Using a variant keeps a single set of models compatible with both backends so
the test suite can run on SQLite while production keeps full JSONB features.
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on PostgreSQL, plain JSON on SQLite (used by the test suite).
JSONVariant = JSONB().with_variant(JSON(), "sqlite")