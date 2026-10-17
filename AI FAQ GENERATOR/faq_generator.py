      "question": "Question text?",
      "answer": "Answer text.",
      "category": "{category}"
    }}
  ]
}}
"""

    user_prompt = f"Source type: {source_type}\n\nSource content:\n{clean_text}"

    try:
        client = Groq(api_key=api_key.strip(), timeout=60.0)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
            timeout=60.0,
        )

        if not response or not response.choices:
            return {"success": False, "error": "The AI model returned an empty response."}

        response_content = response.choices[0].message.content
        if not response_content or not response_content.strip():
            return {"success": False, "error": "The AI model returned empty content."}

        try:
            parsed_data = json.loads(response_content.strip())
        except json.JSONDecodeError:
            logger.exception("Could not parse Groq JSON response.")
            return {
                "success": False,
                "error": "The AI response was not valid JSON. Please try again.",
            }

        if not isinstance(parsed_data, dict):
            return {"success": False, "error": "The AI response has an invalid format."}

        title = parsed_data.get("title")
        if not isinstance(title, str) or not title.strip():
            title = f"{category} FAQs"

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
            item_category = str(item.get("category") or category).strip()

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
        return {"success": False, "error": f"Groq API error: {str(exc)}"}
    except Exception:
        logger.exception("Unexpected FAQ generation error.")
        return {
            "success": False,
            "error": "An unexpected error occurred while generating FAQs.",
        }

