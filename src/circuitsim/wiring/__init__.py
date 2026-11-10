"""Explicit wiring model: attachments, junctions, netlist and routing (no Qt)."""

from circuitsim.wiring.model import (
    Attachment,
    FreeEnd,
    Junction,
    JunctionRef,
    SplitResult,
    TerminalRef,
    Wire,
    WireGraph,
    WireGraphError,
)
from circuitsim.wiring.netlist import GROUND_NODE, WiringNetlist, build_circuit
from circuitsim.wiring.router import route
from circuitsim.wiring.serializer import (
    CircuitDocumentV2,
    SCHEMA_VERSION_V2,
    dict_to_document_v2,
    document_to_dict_v2,
    dumps_document_v2,
    load_document_v2,
    loads_document_v2,
    migrate_v1_to_v2,
    save_document_v2,
)

__all__ = [
    "Attachment",
    "CircuitDocumentV2",
    "FreeEnd",
    "GROUND_NODE",
    "Junction",
    "JunctionRef",
    "SCHEMA_VERSION_V2",
    "SplitResult",
    "TerminalRef",
    "Wire",
    "WireGraph",
    "WireGraphError",
    "WiringNetlist",
    "build_circuit",
    "dict_to_document_v2",
    "document_to_dict_v2",
    "dumps_document_v2",
    "load_document_v2",
    "loads_document_v2",
    "migrate_v1_to_v2",
    "route",
    "save_document_v2",
]
