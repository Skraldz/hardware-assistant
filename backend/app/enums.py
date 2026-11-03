"""Enumerations shared across the database models, schemas and rules.

Kept in one module with no project imports of its own, so every other layer
can depend on it without a cycle.
"""

from enum import StrEnum


class Category(StrEnum):
    """The eight hardware categories a component can belong to.

    Fixed rather than free text: the category selects which specification
    schema applies (schemas/components.py's discriminated union), which
    compatibility rules are relevant, and which slot a component fills in a
    Build. A ninth category would need all three extended.
    """

    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    GPU = "gpu"
    STORAGE = "storage"
    PSU = "psu"
    CASE = "case"
    COOLER = "cooler"


class Condition(StrEnum):
    """What state a component is in.

    `FAULTY` is excluded from recommendations entirely -- the point of the
    field is to keep a broken part in the inventory, for reference, without
    it ever being suggested.
    """

    NEW = "new"
    USED = "used"
    FAULTY = "faulty"


class SpecsSource(StrEnum):
    """Where a component's specifications came from.

    Recorded per component so the user can tell a value they typed from one
    a language model extracted from a web page. Paired with
    `specs_verified`, this is the provenance trail behind the project's main
    caveat: the system can verify compatibility, but not that the
    specifications themselves are correct.
    """

    MANUAL = "manual"
    LLM_EXTRACTED = "llm_extracted"
    WEB_LOOKUP = "web_lookup"
