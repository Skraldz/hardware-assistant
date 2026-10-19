from enum import StrEnum


class Category(StrEnum):
    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    GPU = "gpu"
    STORAGE = "storage"
    PSU = "psu"
    CASE = "case"
    COOLER = "cooler"


class Condition(StrEnum):
    NEW = "new"
    USED = "used"
    FAULTY = "faulty"


class SpecsSource(StrEnum):
    MANUAL = "manual"
    LLM_EXTRACTED = "llm_extracted"
    WEB_LOOKUP = "web_lookup"
