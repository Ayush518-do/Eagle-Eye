"""Server-generated public identifiers.

Format: PREFIX-<12 random hex characters>, for example INS-3F9A1C07B2D4.
Prefixes INS, IMG, F and OBS follow the examples in docs/contracts.md. DREV and ITEM are
not named in the docs (the contract only shows REV-A, which is a display label), so they
are kept distinct from labels. Treat every id as an opaque string: never parse it and never
assume order.
"""
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"
