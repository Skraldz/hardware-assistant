from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.enums import Category
from app.schemas.components import ComponentCreate, ComponentRead, ComponentUpdate

router = APIRouter(prefix="/api/components", tags=["components"])


@router.get("", response_model=list[ComponentRead])
def list_components(
    category: Category | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[models.Component]:
    query = db.query(models.Component)
    if category is not None:
        query = query.filter(models.Component.category == category)
    return query.order_by(models.Component.id).all()


@router.post("", response_model=ComponentRead, status_code=201)
def create_component(payload: ComponentCreate, db: Session = Depends(get_db)) -> models.Component:
    component = models.Component(
        category=Category(payload.specs.category),
        name=payload.name,
        manufacturer=payload.manufacturer,
        quantity=payload.quantity,
        condition=payload.condition,
        specs=payload.specs.model_dump(),
        specs_source=payload.specs_source,
        specs_verified=payload.specs_verified,
        notes=payload.notes,
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


@router.get("/{component_id}", response_model=ComponentRead)
def get_component(component_id: int, db: Session = Depends(get_db)) -> models.Component:
    component = db.get(models.Component, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return component


@router.put("/{component_id}", response_model=ComponentRead)
def update_component(
    component_id: int, payload: ComponentUpdate, db: Session = Depends(get_db)
) -> models.Component:
    component = db.get(models.Component, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Component not found")

    data = payload.model_dump(exclude_unset=True)
    if "specs" in data:
        specs = data.pop("specs")
        component.category = Category(specs["category"])
        component.specs = specs
    for field, value in data.items():
        setattr(component, field, value)

    db.commit()
    db.refresh(component)
    return component


@router.delete("/{component_id}", status_code=204)
def delete_component(component_id: int, db: Session = Depends(get_db)) -> None:
    component = db.get(models.Component, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Component not found")
    db.delete(component)
    db.commit()
