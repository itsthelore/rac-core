"""RAC output layer.

Presentation only: human-readable text, JSON (a stable public contract, ADR-007),
and Markdown templates. Output formatting must not leak into core or service
logic. Renderers are re-exported here so callers can use ``rac.output.render_*``
without depending on the internal split between human/json/templates.
"""

from .human import (
    render_diff_human,
    render_dir_inspect_human,
    render_improve_human,
    render_inspect_human,
    render_inspect_verbose,
    render_portfolio_human,
    render_relationship_validation_human,
    render_relationships_human,
    render_schema_human,
    render_schema_list_human,
    render_stats_human,
    render_unknown_schema,
    render_validation_human,
)
from .json import (
    render_diff_json,
    render_dir_inspect_json,
    render_improve_json,
    render_ingest_json,
    render_inspect_json,
    render_portfolio_json,
    render_relationship_validation_json,
    render_relationships_json,
    render_schema_json,
    render_schema_list_json,
    render_stats_json,
    render_validation_json,
)
from .templates import render_improve_template, render_schema_template

__all__ = [
    "render_diff_human",
    "render_diff_json",
    "render_dir_inspect_human",
    "render_dir_inspect_json",
    "render_improve_human",
    "render_improve_json",
    "render_improve_template",
    "render_ingest_json",
    "render_inspect_human",
    "render_inspect_json",
    "render_inspect_verbose",
    "render_portfolio_human",
    "render_portfolio_json",
    "render_relationship_validation_human",
    "render_relationship_validation_json",
    "render_relationships_human",
    "render_relationships_json",
    "render_schema_human",
    "render_schema_json",
    "render_schema_list_human",
    "render_schema_list_json",
    "render_schema_template",
    "render_stats_human",
    "render_stats_json",
    "render_unknown_schema",
    "render_validation_human",
    "render_validation_json",
]
