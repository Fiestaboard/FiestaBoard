"""FiestaBoard's shared operation layer (issue #1764).

One grammar of named operations, executed the same way whichever AI
surface asked: the streaming chat's ``fiestaboard`` fenced blocks
(:mod:`src.ai.chat_ops`) and the MCP tools (:mod:`src.mcp_server`) both
resolve into the executors registered here. Teaching text about the
board (dimensions, template syntax) is generated once in
:mod:`src.ops.teaching` from real device/engine metadata.
"""

from . import executors, teaching
from .registry import (
    OPERATIONS,
    ClientSideOperationError,
    Operation,
    execute,
    execute_sync,
    get_operation,
    operation_names,
)
from .results import err, ok, rest_detail, serialize

__all__ = [
    "OPERATIONS",
    "ClientSideOperationError",
    "Operation",
    "err",
    "execute",
    "execute_sync",
    "executors",
    "get_operation",
    "ok",
    "operation_names",
    "rest_detail",
    "serialize",
    "teaching",
]
