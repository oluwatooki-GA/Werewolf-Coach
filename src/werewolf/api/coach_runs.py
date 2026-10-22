"""Starting and watching a coach run from the API. SKELETON, not built yet, and probably best left
unbuilt: DESIGN 9 has experiments and the coach run from your machine, and the deployed app only
serves what they produced (`coach.py` reads the history).

If it is ever built:

- `POST /coach/{side}/runs` takes an admin token (a run spends real money on Sonnet and on the
  player model, so it is never public), checks the same spending limits as the command line, saves
  a row in a `coach_runs` table (state "queued") and starts `coach.run.run_coach(...)` as an asyncio
  task. That function is the whole coach: FastAPI only calls it and never sees LangGraph, which is
  the wiring inside `coach/graph.py::run_generation`.
- `GET /coach/runs/{run_id}` reads that row: state (queued, running, finished, stopped, failed),
  the generations finished so far and the money spent.
- A run takes minutes to hours, so it must not live inside one request. On a free host that sleeps
  or restarts, a task in the web process can die half way; a separate worker process, or just the
  command line, is safer. A stopped run saves nothing for the generation in progress and resumes at
  the next one, so a dead task loses little.
"""

from fastapi import APIRouter, HTTPException

from werewolf.api.schemas import CoachRunRequest, CoachRunStatus

router = APIRouter(prefix="/coach", tags=["coach"])
NOT_BUILT = "starting a coach run from the API is not built; use `coach run` on the command line"


@router.post("/{side}/runs", response_model=CoachRunStatus)
def start_run(side: str, request: CoachRunRequest) -> CoachRunStatus:
    raise HTTPException(501, NOT_BUILT)


@router.get("/runs/{run_id}", response_model=CoachRunStatus)
def run_status(run_id: str) -> CoachRunStatus:
    raise HTTPException(501, NOT_BUILT)
