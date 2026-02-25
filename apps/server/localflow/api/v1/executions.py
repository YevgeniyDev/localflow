import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db, get_tools
from ...services.execution_service import ExecutionService
from ..schemas import ErrorOut
from .schemas import ExecuteIn, ExecuteOut

router = APIRouter()


@router.post(
    "/executions",
    response_model=ExecuteOut,
    responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
async def execute(inp: ExecuteIn, db: Session = Depends(get_db), tools=Depends(get_tools)):
    try:
        exe = await ExecutionService(db, tools).execute(
            inp.approval_id,
            inp.tool_name,
            inp.tool_input,
            confirmation=inp.confirmation,
        )
    except ValueError as e:
        message = str(e)
        lowered = message.lower()
        if "not found" in lowered:
            status_code = 404
        elif (
            "changed since approval" in lowered
            or "not approved" in lowered
            or "confirmation" in lowered
            or "risk tool" in lowered
        ):
            status_code = 409
        else:
            status_code = 400
        raise HTTPException(status_code=status_code, detail=message)

    try:
        result_obj = json.loads(exe.result_json)
    except Exception:
        result_obj = {"raw": exe.result_json}
    return {"execution_id": exe.id, "status": exe.status, "result": result_obj}
