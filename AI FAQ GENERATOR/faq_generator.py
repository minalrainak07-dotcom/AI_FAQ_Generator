
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
    """
    Generate FAQs using the Groq AI API.

    Returns:
        dict: Success response with title and FAQs,
              or an error response.
    """

    # 1. Check API key
    api_key = os.getenv("GROQ_API_KEY")

    if (
        not api_key
        or not api_key.strip()
        or api_key.strip() == "your_groq_api_key_here"
    ):
        return {
            "success": False,
            "error": (
                "Groq API key is missing or not configured. "
                "Please set GROQ_API_KEY in Render Environment."
            ),
        }

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # 2. Validate source text
    if not source_text or not str(source_text).strip():
        return {
            "success": False,
            "error": "Source text or topic is empty. Please provide content.",
        }

    # 3. Validate FAQ count
    try:
        num_faqs = int(num_faqs)
    except (TypeError, ValueError):
        return {
            "success": False,
            "error": "FAQ count must be a number.",
        }

    if num_faqs not in (5, 10, 15):
        return {
            "success": False,
            "error": "Please select 5, 10, or 15 FAQs.",
        }

    clean_text = str(source_text).strip()

    if len(clean_text) > 6000:
        clean_text = (
            clean_text[:6000]
            + "\n\n[Source text truncated to 6000 characters.]"
        )

    # 4. Answer length settings
    length_guides = {
        "short": "1 to 2 concise sentences, approximately 20-40 words",
        "medium": "3 to 5 informative sentences, approximately 50-100 words",
        "detailed": (
            "one comprehensive paragraph with context, "
            "approximately 120-200 words"
        ),
    }

    selected_length = length_guides.get(
        str(answer_length).lower(),
        length_guides["medium"],
    )

    # 5. Source instructions
    if source_type in ("pdf", "text"):
        source_instruction = (
            "Base all questions and answers strictly on the factual "
            "information provided in the source text. Do not invent "
            "facts that are not present in the source."
        )
    else:
        source_instruction = (
            "Generate accurate, useful questions and answers based "
            "on your knowledge of the specified topic."
        )

    # 6. AI prompts
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
      "question": "Question text?",
      "answer": "Answer text.",
      "category": "{category}"
    }}
  ]
}}
"""

    user_prompt = (
        f"Source type: {source_type}\n\n"
        f"Source content:\n{clean_text}"
    )

    # 7. Call Groq API and process response
    try:
        client = Groq(
            api_key=api_key.strip(),
            timeout=60.0,
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
            timeout=60.0,
        )

        if not response or not response.choices:
            return {
                "success": False,
                "error": "The AI model returned an empty response.",
            }

        response_content = response.choices[0].message.content

        if not response_content or not response_content.strip():
            return {
                "success": False,
                "error": "The AI model returned empty content.",
            }

        # 8. Parse JSON
        try:
            parsed_data = json.loads(response_content.strip())
        except json.JSONDecodeError:
            logger.exception("Could not parse Groq JSON response.")
            return {
                "success": False,
                "error": "The AI response was not valid JSON. Please try again.",
            }

        if not isinstance(parsed_data, dict):
            return {
                "success": False,
                "error": "The AI response has an invalid format.",
            }

        # 9. Validate title
        title = parsed_data.get("title")

        if not isinstance(title, str) or not title.strip():
            title = f"{category} FAQs"

        # 10. Validate FAQ list
        raw_faqs = parsed_data.get("faqs")

        if not isinstance(raw_faqs, list):
            return {
                "success": False,
                "error": "The AI response did not contain a valid FAQ list.",
            }

        validated_faqs = []

        for item in raw_faqs:
            if not isinstance(item, dict):
                continue

            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            item_category = str(
                item.get("category") or category
            ).strip()

            if question and answer:
                validated_faqs.append(
                    {
                        "question": question,
                        "answer": answer,
                        "category": item_category or category,
                    }
                )

        if not validated_faqs:
            return {
                "success": False,
                "error": "No valid question-and-answer pairs were generated.",
            }

        # Return the requested number of FAQs
        validated_faqs = validated_faqs[:num_faqs]

        return {
            "success": True,
            "data": {
                "title": title.strip(),
                "faqs": validated_faqs,
            },
        }

    except AuthenticationError:
        logger.exception("Groq authentication failed.")
        return {
            "success": False,
            "error": "Invalid Groq API key. Check the Render environment.",
        }

    except RateLimitError:
        logger.exception("Groq rate limit exceeded.")
        return {
            "success": False,
            "error": "Groq rate limit exceeded. Please try again later.",
        }

    except APITimeoutError:
        logger.exception("Groq API request timed out.")
        return {
            "success": False,
            "error": "Groq request timed out. Try shorter source text.",
        }

    except APIConnectionError:
        logger.exception("Could not connect to Groq.")
        return {
            "success": False,
            "error": "Could not connect to the Groq service.",
        }

    except APIError as exc:
        logger.exception("Groq API error.")
        return {
            "success": False,
            "error": f"Groq API error: {str(exc)}",
        }

    except Exception:
        logger.exception("Unexpected FAQ generation error.")
        return {
            "success": False,
            "error": "An unexpected error occurred while generating FAQs.",
        }
