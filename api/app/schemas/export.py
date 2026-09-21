from typing import Literal

# Query-parameter types for GET /projects/{project_id}/export -- kept here
# (rather than inline in the route) so the allowed values are documented
# in one obvious place, the same pattern used elsewhere in schemas/.
ExportFormat = Literal["jsonl", "csv"]
ExportStatusFilter = Literal["approved", "generated", "rejected", "all"]
