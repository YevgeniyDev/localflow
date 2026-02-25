from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import get_db, get_tools
from ...services.execution_service import ExecutionService

router = APIRouter()

class ExecuteIn(BaseModel):
    approval_id: str
    tool_name: str
    tool_input: dict

@router.post("/executions")
async def execute(inp: ExecuteIn, db: Session = Depends(get_db), tools=Depends(get_tools)):
    exe = await ExecutionService(db, tools).execute(inp.approval_id, inp.tool_name, inp.tool_input)
    return {"execution_id": exe.id, "status": exe.status, "result": exe.result_json}