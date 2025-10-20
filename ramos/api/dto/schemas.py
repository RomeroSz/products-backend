# products-backend/ramos/dto/schemas.py
"""
Modelos ligeros de contrato (referenciales).
Pueden servir para documentación o migrar a serializadores/DRF serializers en el futuro.
"""

from typing import TypedDict, List, Optional


class NodeRef(TypedDict):
    id: str
    code: str
    name: str


class ModalidadItem(TypedDict):
    id: str
    code: str
    name: str
    displayName: str


class ModalidadResponse(TypedDict):
    node: NodeRef
    modalidades: List[ModalidadItem]


class ContableRef(TypedDict):
    id: str
    code: str
    name: str


class ContablesResponse(TypedDict):
    node: NodeRef
    contables: List[ContableRef]
    source: str  # "direct" | "inherited"


class ValidatePathResponse(TypedDict):
    ok: bool
    leaf: NodeRef
    levels: List[int]
    codes: List[str]
    requires_modalidad: bool
    allowed_modalidades: List[str]
    modalidades: Optional[List[str]]
