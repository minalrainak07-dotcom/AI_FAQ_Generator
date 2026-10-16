import os
import json
import logging
from groq import Groq, AuthenticationError, RateLimitError, APIError, APITimeoutError, APIConnectionError

logger = logging.getLogger(__name__)


def generate_faqs(source_text, source_type='text', num_faqs=5, difficulty='intermediate',
                  answer_length='medium', language='English', category='General Knowledge'):
    """
    Generate FAQs using the Groq AI API.

    Parameters:
        source_text (str): Content or topic prompt.
        source_type (str): 'pdf', 'text', or 'topic'.
        num_faqs (int): Target number of FAQs to generate.
        difficulty (str): 'beginner', 'intermediate', or 'advanced'.
        answer_length (str): 'short', 'medium', or 'detailed'.
        language (str): Output language (e.g., 'English', 'Hindi', etc.).
        category (str): Category domain for the FAQs.

    Returns:
        dict: {"success": True, "data": {"title": ..., "faqs": [...]}}
              or {"success": False, "error": "descriptive message"}
    """
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key or not api_key.strip() or api_key == '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':
        return {
            "success": False,
            "error": "Groq API key is missing or not configured. Please set GROQ_API_KEY in your .env file."
        }

    model = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')

    if not source_text or not str(source_text).strip():
        return {
            "success": False,
            "error": "Source text or topic is empty. Please provide content to generate FAQs."
        }

    # Truncate source_text to 6000 characters if too long
    clean_text = str(source_text).strip()
    if len(clean_text) > 6000:
        clean_text = clean_text[:6000] + "\n\n[Note: Source text was truncated to 6000 characters for processing.]"

    # Map answer length guidelines
    length_guides = {
        'short': '1 to 2 concise sentences (approx. 20-40 words)',
        'medium': '3 to 5 informative sentences (approx. 50-100 words)',
        'detailed': 'a comprehensive full paragraph with in-depth explanation and clear context (approx. 120-200 words)'
    }
    selected_length = length_guides.get(str(answer_length).lower(), '3 to 5 sentences')

    # System instruction tailored by source_type
    if source_type in ['pdf', 'text']:
        source_instruction = (
            "Base all questions and answers strictly on the factual information provided in the source text. "
            "Do not hallucinate facts outside the provided text."
        )
    else:  # 'topic'
        source_instruction = (
            "Generate accurate, comprehensive, and well-researched questions and answers "
            "based on deep knowledge of the specified topic."
        )

    system_prompt = f"""You are an expert educational and technical FAQ generator.
Your objective is to generate exactly {num_faqs} high-quality, relevant frequently asked questions and answers.

GUIDELINES:
1. Source Guidance: {source_instruction}
2. Language: All questions, answers, and the overall title MUST be written in {language}.
3. Difficulty Level: {difficulty.capitalize()} level (adjust terminology, concepts, and depth accordingly).
4. Answer Length: Each answer must be {selected_length}.
5. Category: Focus primarily on the category '{category}', assigning relevant sub-categories or '{category}' to each FAQ.
6. Uniqueness: Avoid duplicate or overlapping questions. Each question must explore a distinct aspect.
7. Format: Return ONLY a valid JSON object. No Markdown code fences, no explanations outside the JSON.

Expected JSON structure:
{{
  "title": "A concise, descriptive title for this FAQ collection in {language}",
  "faqs": [
    {{
      "question": "Question text here?",
      "answer": "Answer text here adhering to specified length.",
      "category": "{category}"
    }}
  ]
}}"""

    user_prompt = f"Source Content ({source_type}):\n\n{clean_text}"

    try:
        client = Groq(api_key=api_key.strip(), timeout=60.0)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
            timeout=60.0
        )

        if not response or not response.choices:
            return {
                "success": False,
                "error": "Received an empty response from the AI model."
            }

        response_content = response.choices[0].message.content
        if not response_content or not response_content.strip():
            return {
                "success": False,
                "error": "The AI model returned empty content."
            }

        # Parse JSON
        try:
            parsed_data = json.loads(response_content.strip())
        except json.JSONDecodeError as jde:
            logger.error(f"JSON parsing error: {jde}. Raw response: {response_content}")
            return {
                "success": False,
                "error": f"Failed to parse AI response as JSON: {str(jde)}"
            }

        # Validate title
        title = parsed_data.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            fallback_title = f"{category} FAQs"
            if source_type == 'topic':
                fallback_title = f"{clean_text[:40]} FAQs"
            title = fallback_title

        # Validate faqs list
        raw_faqs = parsed_data.get("faqs")
        if not isinstance(raw_faqs, list) or len(raw_faqs) == 0:
            return {
                "success": False,
                "error": "AI response did not contain a valid list of FAQs."
            }

        validated_faqs = []
        for index, item in enumerate(raw_faqs):
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            item_cat = str(item.get("category", category or "General Knowledge")).strip()
            if not item_cat:
                item_cat = category or "General Knowledge"

            if question and answer:
                validated_faqs.append({
                    "question": question,
                    "answer": answer,
                    "category": item_cat
                })

        if not validated_faqs:
            return {
                "success": False,
                "error": "No valid question-answer pairs were extracted from the AI response."
            }

        return {
            "success": True,
            "data": {
                "title": title.strip(),
                "faqs": validated_faqs
            }
        }

    except AuthenticationError as e:
        logger.error(f"Groq Authentication error: {e}")
        return {
            "success": False,
            "error": "Authentication failed. Invalid Groq API key."
        }
    except RateLimitError as e:
        logger.error(f"Groq Rate limit error: {e}")
        return {
            "success": False,
            "error": "Groq rate limit exceeded. Please wait a moment before trying again."
        }
    except APITimeoutError as e:
        logger.error(f"Groq API timeout error: {e}")
        return {
            "success": False,
            "error": "Groq AI request timed out after 60 seconds. Please try again with shorter text."
        }
    except APIConnectionError as e:
        logger.error(f"Groq API connection error: {e}")
        return {
            "success": False,
            "error": "Network connection error while connecting to Groq AI service."
        }
    except APIError as e:
        logger.error(f"Groq API error: {e}")
        return {
            "success": False,
            "error": f"Groq API returned an error: {getattr(e, 'message', str(e))}"
        }
    except Exception as e:
        logger.error(f"Unexpected error during FAQ generation: {e}")
        return {
            "success": False,
            "error": f"An unexpected error occurred while generating FAQs: {str(e)}"
        }
