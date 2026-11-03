"""Endpoints for the inventory, and for looking a component up on the web.

The lookup flow is deliberately three steps -- search, extract, then the
user confirms -- so nothing a language model produced is stored without a
person having seen it.
"""

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
    ClearInventoryRequest,
    ClearInventoryResponse,
    ComponentCreate,
    ComponentRead,
    ComponentUpdate,
    ReseedRequest,
    ReseedResponse,
)
from app.schemas.search import (
    CategoryGuess,
    ExtractRequest,
    ExtractResponse,
    SearchRequest,
    SearchResponse,
)
from app.search.client import SearchClient, SearchUnavailableError, get_search_client
from app.search.page_fetch import PageFetcher, get_page_fetcher
from app.seed import SEED_COMPONENTS, _component_from_seed_item

router = APIRouter(prefix="/api/components", tags=["components"])


@router.get("", response_model=list[ComponentRead])
def list_components(
    category: Category | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[models.Component]:
    """List inventory components, newest first.

    Args:
        category: Optional filter; omitted returns every category.
        db: Database session.

    Returns:
        list[Component]: Matching components.
    """
    query = db.query(models.Component)
    if category is not None:
        query = query.filter(models.Component.category == category)
    return query.order_by(models.Component.id).all()


@router.post("", response_model=ComponentRead, status_code=201)
def create_component(payload: ComponentCreate, db: Session = Depends(get_db)) -> models.Component:
    """Add one component to the inventory.

    The category is taken from the specs payload rather than sent
    separately, so the two can never disagree.

    Args:
        payload: The component to create, including its category-specific specs.
        db: Database session.

    Returns:
        Component: The created row, with its assigned id.
    """
    component = models.Component(
        category=Category(payload.specs.category),
        name=payload.name,
        manufacturer=payload.manufacturer,
        release_year=payload.release_year,
        quantity=payload.quantity,
        condition=payload.condition,
        specs=payload.specs.model_dump(),
        specs_source=payload.specs_source,
        specs_verified=payload.specs_verified,
        source_url=payload.source_url,
        notes=payload.notes,
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


@router.post("/clear", response_model=ClearInventoryResponse)
def clear_inventory(payload: ClearInventoryRequest, db: Session = Depends(get_db)) -> ClearInventoryResponse:
    """Delete every component and every saved build.

    Args:
        payload: Must carry confirm=True; the step exists because this is
            irreversible and there is no undo.
        db: Database session.

    Returns:
        dict: Counts of deleted components and builds.

    Raises:
        HTTPException: 400 when confirm is not True.
    """
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm: true is required to clear the inventory.")
    # Saved builds reference components by id and are meaningless once every
    # component is gone, so they're cleared together, in one transaction.
    deleted_components = db.query(models.Component).delete()
    deleted_builds = db.query(models.SavedBuild).delete()
    db.commit()
    return ClearInventoryResponse(deleted_components=deleted_components, deleted_builds=deleted_builds)


@router.post("/reseed", response_model=ReseedResponse)
def reseed_inventory(payload: ReseedRequest, db: Session = Depends(get_db)) -> ReseedResponse:
    """Add the demo components on top of the current inventory.

    Adds rather than replaces, and skips any component whose name is already
    present, so it is safe to run twice.

    Args:
        payload: Must carry confirm=True.
        db: Database session.

    Returns:
        dict: How many demo components were added and how many skipped.

    Raises:
        HTTPException: 400 when confirm is not True.
    """
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm: true is required to reseed the inventory.")
    # Adds on top of whatever's already there rather than replacing it --
    # matched by (category, name) so clicking this more than once never
    # creates duplicate rows for seed items already present.
    existing = {
        (category, name)
        for category, name in db.query(models.Component.category, models.Component.name).all()
    }
    added = 0
    for item in SEED_COMPONENTS:
        key = (item["category"], item["name"])
        if key in existing:
            continue
        db.add(_component_from_seed_item(item))
        existing.add(key)
        added += 1
    db.commit()
    return ReseedResponse(added=added, skipped=len(SEED_COMPONENTS) - added)


@router.post("/search", response_model=SearchResponse)
def search_components(
    payload: SearchRequest, search_client: SearchClient = Depends(get_search_client)
) -> SearchResponse:
    """Find candidate web pages documenting a component's specs.

    Args:
        payload: The component name to search for.
        search_client: SearXNG client; replaced by a fake in tests.

    Returns:
        SearchResponse: Up to MAX_CANDIDATES pages for the user to choose from.

    Raises:
        HTTPException: 503 when SearXNG cannot be reached, 404 when the search
            returns nothing -- deliberately an error rather than a silent fall
            back to the model guessing.
    """
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
    payload: ExtractRequest,
    llm_client: LLMClient = Depends(get_llm_client),
    page_fetcher: PageFetcher = Depends(get_page_fetcher),
) -> ExtractResponse:
    """Extract a component's specifications for the user to confirm.

    Two LLM calls: a tiny category-only schema first, then a flat
    category-specific schema for the fields. Ollama's structured-output
    grammar handles a plain object far more reliably than the full
    discriminated union, which was leading the model to emit little beyond
    the category itself.

    Args:
        payload: Component name, the chosen search candidate, and the other
            candidates from the same search (pooled for extra context).
        llm_client: Ollama client; replaced by a fake in tests.
        page_fetcher: Fetches the chosen candidate's page text; faked in tests.

    Returns:
        ExtractResponse: The extracted specs, release year, the source URL
            actually fetched, and whether the model answered cleanly, retried
            or fell back.

    Raises:
        HTTPException: 400 when web lookup is enabled but no candidate was
            given; 422 when the category or the specs could not be determined
            even after a retry, so the user enters them manually.
    """
    settings = get_settings()
    web_snippet: str | None = None
    specs_source = SpecsSource.LLM_EXTRACTED

    if settings.enable_web_lookup:
        if payload.candidate is None:
            raise HTTPException(
                status_code=400,
                detail="ENABLE_WEB_LOOKUP=true requires a 'candidate' chosen via /api/components/search.",
            )
        # A single search result's snippet is frequently too short to
        # contain every spec (e.g. a product's launch-date blurb vs. its
        # VRAM/wattage) -- the other results for the same query often have
        # what this one is missing, so all of them are merged into the
        # extraction context rather than using the chosen one alone.
        all_candidates = [payload.candidate, *payload.other_candidates]
        web_snippet = "\n\n".join(f"{c.title}\n{c.snippet}" for c in all_candidates)

        # A snippet is a short preview the search engine generated, not the
        # page itself -- a spec table/bullet list often sits further down
        # the real page than any snippet reaches. Best-effort: fetching the
        # chosen candidate's actual page (not the others, to keep this one
        # extra request) and prepending its cleaned text gives the LLM a
        # much larger, more complete slice of the real content to draw
        # from; a fetch failure just leaves web_snippet as it already was.
        page_text = page_fetcher.fetch(payload.candidate.url)
        if page_text:
            web_snippet = (
                f'Full page content for "{payload.candidate.title}":\n{page_text}\n\n'
                f"--- Other search results (short previews only) ---\n{web_snippet}"
            )
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
    extracted_fields = extracted.model_dump()
    release_year = extracted_fields.pop("release_year", None)
    specs = spec_class.model_validate(extracted_fields)

    return ExtractResponse(
        name=payload.name,
        specs=specs,
        release_year=release_year,
        specs_source=specs_source,
        source_url=payload.candidate.url if payload.candidate else None,
        llm_used=combine_status(category_status, specs_status),
    )


@router.get("/{component_id}", response_model=ComponentRead)
def get_component(component_id: int, db: Session = Depends(get_db)) -> models.Component:
    """Fetch one component by id.

    Args:
        component_id: Primary key.
        db: Database session.

    Returns:
        Component: The matching row.

    Raises:
        HTTPException: 404 when no component has that id.
    """
    component = db.get(models.Component, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return component


@router.put("/{component_id}", response_model=ComponentRead)
def update_component(
    component_id: int, payload: ComponentUpdate, db: Session = Depends(get_db)
) -> models.Component:
    """Update some of a component's fields.

    Only the fields present in the payload are changed. Sending new specs
    also updates the stored category, keeping the two in step.

    Args:
        component_id: Primary key.
        payload: The fields to change.
        db: Database session.

    Returns:
        Component: The updated row.

    Raises:
        HTTPException: 404 when no component has that id.
    """
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
    """Delete one component.

    Args:
        component_id: Primary key.
        db: Database session.

    Raises:
        HTTPException: 404 when no component has that id.
    """
    component = db.get(models.Component, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Component not found")
    db.delete(component)
    db.commit()
