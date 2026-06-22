from prompts import summarise as _summarise_from_prompts
from pydantic import BaseModel


def summarise(section: str, raw_data: dict) -> BaseModel:
    """
    Routes raw scraped data to the correct prompt function
    and returns a populated Pydantic model with AI-generated fields.

    Args:
        section:  'papers' | 'news' | 'tools' | 'benchmarks' | 'talks'
        raw_data: dict of raw scraped fields matching the section schema

    Returns:
        Populated Pydantic model instance (ResearchPaper, AINewsArticle, etc.)
        with all AI-generated fields filled in.

    Raises:
        ValueError: if section is not recognised
        Exception:  if Groq API call fails (caller handles retry)
    """
    return _summarise_from_prompts(section, raw_data)