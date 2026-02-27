from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from localflow.api.deps import get_rag
from localflow.rag.service import RagService

router = APIRouter(tags=["rag"])


class RagPermissionIn(BaseModel):
    path: str


class RagPermissionsOut(BaseModel):
    roots: list[str]


class RagSetPermissionsIn(BaseModel):
    roots: list[str]


class RagIndexIn(BaseModel):
    roots: list[str] | None = None
    max_files: int = Field(default=1500, ge=1, le=20000)


class RagSearchIn(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=12)
    roots: list[str] | None = None


class RagHitOut(BaseModel):
    path: str
    score: float
    snippet: str


class RagSearchOut(BaseModel):
    hits: list[RagHitOut]


class RagListDirsIn(BaseModel):
    path: str | None = None


@router.get("/rag/permissions", response_model=RagPermissionsOut)
def list_permissions(rag: RagService = Depends(get_rag)):
    return {"roots": rag.list_permissions()}


@router.get("/rag/drives")
def list_drives(rag: RagService = Depends(get_rag)):
    return {"drives": rag.list_available_drives()}


@router.post("/rag/list_dirs")
def list_dirs(inp: RagListDirsIn, rag: RagService = Depends(get_rag)):
    try:
        dirs = rag.list_subdirs(inp.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"dirs": dirs}


@router.post("/rag/permissions/grant", response_model=RagPermissionsOut)
def grant_permission(inp: RagPermissionIn, rag: RagService = Depends(get_rag)):
    try:
        roots = rag.grant_permission(inp.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"roots": roots}


@router.post("/rag/permissions/revoke", response_model=RagPermissionsOut)
def revoke_permission(inp: RagPermissionIn, rag: RagService = Depends(get_rag)):
    roots = rag.revoke_permission(inp.path)
    return {"roots": roots}


@router.post("/rag/permissions/set", response_model=RagPermissionsOut)
def set_permissions(inp: RagSetPermissionsIn, rag: RagService = Depends(get_rag)):
    try:
        roots = rag.set_permissions(inp.roots)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"roots": roots}


@router.get("/rag/status")
def rag_status(rag: RagService = Depends(get_rag)):
    return rag.status()


@router.post("/rag/index")
def rag_index(inp: RagIndexIn, rag: RagService = Depends(get_rag)):
    try:
        return rag.rebuild_index(roots=inp.roots, max_files=inp.max_files)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rag/search", response_model=RagSearchOut)
def rag_search(inp: RagSearchIn, rag: RagService = Depends(get_rag)):
    try:
        hits = rag.search(inp.query, top_k=inp.top_k, roots=inp.roots)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "hits": [
            {"path": h.path, "score": round(h.score, 4), "snippet": h.snippet}
            for h in hits
        ]
    }
