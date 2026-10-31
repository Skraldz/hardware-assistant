"""The "Builds" tab: save a recommended build for later, and optionally mark
it as physically assembled -- which decrements the inventory quantity of
each component it used by 1, so a component that's now built into a PC stops
showing up as available stock for future recommendations.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.schemas.builds import CompleteBuildResponse, SavedBuildCreate, SavedBuildRead

router = APIRouter(prefix="/api/builds", tags=["builds"])


@router.get("", response_model=list[SavedBuildRead])
def list_builds(db: Session = Depends(get_db)) -> list[models.SavedBuild]:
    return db.query(models.SavedBuild).order_by(models.SavedBuild.id.desc()).all()


@router.post("", response_model=SavedBuildRead, status_code=201)
def save_build(payload: SavedBuildCreate, db: Session = Depends(get_db)) -> models.SavedBuild:
    build = models.SavedBuild(
        name=payload.name,
        components=[c.model_dump(mode="json") for c in payload.components],
        reason=payload.reason,
    )
    db.add(build)
    db.commit()
    db.refresh(build)
    return build


@router.delete("/{build_id}", status_code=204)
def delete_build(build_id: int, db: Session = Depends(get_db)) -> None:
    build = db.get(models.SavedBuild, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="Saved build not found")
    db.delete(build)
    db.commit()


@router.post("/{build_id}/complete", response_model=CompleteBuildResponse)
def complete_build(build_id: int, db: Session = Depends(get_db)) -> CompleteBuildResponse:
    build = db.get(models.SavedBuild, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="Saved build not found")
    if build.completed:
        raise HTTPException(status_code=400, detail="This build is already marked complete.")

    removed_ids: list[int] = []
    for entry in build.components:
        component = db.get(models.Component, entry["id"])
        if component is None or component.quantity <= 0:
            # Already deleted, or already consumed by an earlier completed
            # build -- nothing left to decrement, not an error.
            continue
        component.quantity -= 1
        removed_ids.append(component.id)

    build.completed = True
    build.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(build)
    return CompleteBuildResponse(id=build.id, completed=build.completed, removed_component_ids=removed_ids)
