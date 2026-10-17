import os
import json
import logging

from groq import (
    Groq,
    AuthenticationError,
    RateLimitError,
    APIError,
    APITimeoutError,
    APIConnectionError,
)

logger = logging.getLogger(__name__)


def generate_faqs(
    source_text,
    source_type="text",
    num_faqs=5,
    difficulty="intermediate",
    answer_length="medium",
    language="English",
    category="General Knowledge",
):
    """Generate FAQs using the Groq API and return a structured result."""

    # Keep the API key in Render Environment, never hard-code it here.
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or not api_key.strip() or api_key.strip() == "your_groq_api_key_here":
        return {
            "success": False,
            "error": "Groq API key is missing or not configured. Please set GROQ_API_KEY in Render Environment.",
        }

    # Fixed model ID so an incorrect GROQ_MODEL environment value cannot override it.
    model = "openai/gpt-oss-120b"

    if not source_text or not str(source_text).strip():
        return {
            "success": False,
            "error": "Source text or topic is empty. Please provide content.",
        }

    try:
        num_faqs = int(num_faqs)
    except (TypeError, ValueError):
        return {"success": False, "error": "FAQ count must be a number."}

    if num_faqs not in (5, 10, 15):
        return {"success": False, "error": "Please select 5, 10, or 15 FAQs."}

    clean_text = str(source_text).strip()
    if len(clean_text) > 6000:
        clean_text = clean_text[:6000] + "\n\n[Source text truncated to 6000 characters.]"

    length_guides = {
        "short": "1 to 2 concise sentences, approximately 20-40 words",
        "medium": "3 to 5 informative sentences, approximately 50-100 words",
        "detailed": "one comprehensive paragraph with context, approximately 120-200 words",
    }
    selected_length = length_guides.get(
        str(answer_length).lower(), length_guides["medium"]
    )

    if source_type in ("pdf", "text"):
        source_instruction = (
            "Base all questions and answers strictly on the factual information "
            "provided in the source text. Do not invent facts that are not present "
            "in the source."
        )
    else:
        source_instruction = (
            "Generate accurate, useful questions and answers based on your "
            "knowledge of the specified topic."
        )

    system_prompt = f"""
You are an expert educational and technical FAQ generator.
Generate exactly {num_faqs} unique FAQs.

Rules:
1. {source_instruction}
2. Write all questions, answers, and the title in {language}.
3. Difficulty level: {difficulty}.
4. Each answer should be {selected_length}.
5. Main category: {category}.
6. Avoid duplicate or overlapping questions.
7. Return only a valid JSON object.
8. The faqs value must be a JSON array.

Required JSON structure:
{{
  "title": "FAQ collection title",
  "faqs": [
    {{
