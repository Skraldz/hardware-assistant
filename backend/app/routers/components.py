from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import get_db
from app.enums import Category, SpecsSource
from app.llm.client import LLMClient, get_llm_client
from app.llm.parsing import call_llm_with_retry, combine_status
from app.llm.prompts import (
    CATEGORY_SYSTEM_PROMPT,
    EXTRACT_SYSTEM_PROMPT,
    build_category_prompt,
    build_extract_prompt,
)
from app.schemas.components import (
    EXTRACT_SCHEMA_BY_CATEGORY,
    SPEC_CLASS_BY_CATEGORY,
    ComponentCreate,
    ComponentRead,
    ComponentUpdate,
)
from app.schemas.search import (
    CategoryGuess,
    ExtractRequest,
    ExtractResponse,
    SearchRequest,
    SearchResponse,
)
from app.search.client import SearchClient, SearchUnavailableError, get_search_client

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


@router.post("/search", response_model=SearchResponse)
def search_components(
    payload: SearchRequest, search_client: SearchClient = Depends(get_search_client)
) -> SearchResponse:
    settings = get_settings()
    if not settings.enable_web_lookup:
        raise HTTPException(
            status_code=400,
            detail="Web lookup is disabled (ENABLE_WEB_LOOKUP=false). "
            "Call /api/components/extract directly with the name.",
        )
    try:
        candidates = search_client.search(payload.name)
    except SearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"No search results found for '{payload.name}'. Enter the specs manually.",
        )
    return SearchResponse(query=payload.name, candidates=candidates)


@router.post("/extract", response_model=ExtractResponse)
def extract_component_specs(
    payload: ExtractRequest, llm_client: LLMClient = Depends(get_llm_client)
) -> ExtractResponse:
    settings = get_settings()
    web_snippet: str | None = None
    specs_source = SpecsSource.LLM_EXTRACTED

    if settings.enable_web_lookup:
        if payload.candidate is None:
            raise HTTPException(
                status_code=400,
                detail="ENABLE_WEB_LOOKUP=true requires a 'candidate' chosen via /api/components/search.",
            )
        web_snippet = f"{payload.candidate.title}\n{payload.candidate.snippet}"
        specs_source = SpecsSource.WEB_LOOKUP

    # Two LLM calls instead of one: a tiny category-only schema first, then a
    # flat category-specific schema for the fields. Ollama's structured-output
    # grammar handles a plain object far more reliably than the full
    # discriminated-union schema, which was leading the model to emit little
    # beyond "category" itself (see docs/ai-log.md).
    guess, category_status = call_llm_with_retry(
        llm_client,
        system=CATEGORY_SYSTEM_PROMPT,
        build_prompt=lambda error: build_category_prompt(
            payload.name, web_snippet=web_snippet, error_feedback=error
        ),
        schema=CategoryGuess,
        fallback=None,
    )
    if guess is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not determine the hardware category for '{payload.name}'. Enter it manually.",
        )

    spec_class = SPEC_CLASS_BY_CATEGORY[guess.category]
    extract_schema = EXTRACT_SCHEMA_BY_CATEGORY[guess.category]
    extracted, specs_status = call_llm_with_retry(
        llm_client,
        system=EXTRACT_SYSTEM_PROMPT,
        build_prompt=lambda error: build_extract_prompt(
            payload.name, guess.category.value, web_snippet=web_snippet, error_feedback=error
        ),
        schema=extract_schema,
        fallback=None,
    )
    if extracted is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract specifications for '{payload.name}'. Enter them manually.",
        )
    specs = spec_class.model_validate(extracted.model_dump())

    return ExtractResponse(
        name=payload.name,
        specs=specs,
        specs_source=specs_source,
        llm_used=combine_status(category_status, specs_status),
    )


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
