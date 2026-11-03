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
    """List saved builds, newest first.

    Args:
        db: Database session.

    Returns:
        list[SavedBuild]: Every saved build.
    """
    return db.query(models.SavedBuild).order_by(models.SavedBuild.id.desc()).all()


@router.post("", response_model=SavedBuildRead, status_code=201)
def save_build(payload: SavedBuildCreate, db: Session = Depends(get_db)) -> models.SavedBuild:
    """Save a build the user liked, with the ask that produced it.

    Args:
        payload: Name, the components in the build, and the original
            free-text purpose.
        db: Database session.

    Returns:
        SavedBuild: The created row.
    """
    build = models.SavedBuild(
        name=payload.name,
        components=[c.model_dump(mode="json") for c in payload.components],
        purpose=payload.purpose,
        reason=payload.reason,
    )
    db.add(build)
    db.commit()
    db.refresh(build)
    return build


@router.delete("/{build_id}", status_code=204)
def delete_build(build_id: int, db: Session = Depends(get_db)) -> None:
    """Delete one saved build, leaving the inventory untouched.

    Args:
        build_id: Primary key.
        db: Database session.

    Raises:
        HTTPException: 404 when no saved build has that id.
    """
    build = db.get(models.SavedBuild, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="Saved build not found")
    db.delete(build)
    db.commit()


@router.post("/{build_id}/complete", response_model=CompleteBuildResponse)
def complete_build(build_id: int, db: Session = Depends(get_db)) -> CompleteBuildResponse:
    """Mark a saved build as physically assembled.

    Decrements the quantity of every component used, since those parts are
    now inside a machine rather than available for another build.

    Args:
        build_id: Primary key.
        db: Database session.

    Returns:
        dict: The build id, its completed flag, and the ids whose quantity
            was reduced.

    Raises:
        HTTPException: 404 when no saved build has that id.
    """
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
