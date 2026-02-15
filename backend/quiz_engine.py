import requests
import json
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """
You are an expert Game Designer. Your goal is to take a user topic and generate a {num_questions}-question quiz formatted as JSON.
Difficulty: {difficulty} - {difficulty_text}
Mix question types: most should be multiple choice (4 options), but include 2-3 True/False questions.
For True/False questions, use exactly 2 options: ["True", "False"] with answer_index 0 or 1.
You MUST return a JSON object ONLY, with the following structure:
{{
  "quiz_title": "string",
  "questions": [
    {{
      "id": 1,
      "text": "The question text",
      "options": ["A", "B", "C", "D"],
      "answer_index": 0,
      "image_prompt": "A detailed descriptive prompt for an image generator that depicts the subject of this question."
    }}
  ]
}}
Do not include any other text before or after the JSON.
"""

DIFFICULTY_INSTRUCTIONS = {
    "easy": "Generate simple, factual questions suitable for beginners. Keep language clear and answers obvious.",
    "medium": "Generate moderately challenging questions that test solid understanding of the topic.",
    "hard": "Generate challenging questions that test deep knowledge, nuance, and critical thinking.",
}


def _build_system_prompt(difficulty: str, num_questions: int) -> str:
    difficulty_text = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    return SYSTEM_PROMPT_TEMPLATE.format(
        num_questions=num_questions,
        difficulty=difficulty.upper(),
        difficulty_text=difficulty_text,
    )


def _validate_quiz(quiz_data: dict, attempt: int) -> bool:
    if not isinstance(quiz_data, dict):
        logger.warning("Attempt %d: LLM returned non-dict type: %s", attempt, type(quiz_data).__name__)
        return False
    if "questions" not in quiz_data or not isinstance(quiz_data["questions"], list):
        logger.warning("Attempt %d: Missing or invalid 'questions' field", attempt)
        return False
    if len(quiz_data["questions"]) == 0:
        logger.warning("Attempt %d: Empty questions list", attempt)
        return False

    for q in quiz_data["questions"]:
        if not all(k in q for k in ("id", "text", "options", "answer_index")):
            logger.warning("Attempt %d: Question missing required fields: %s", attempt, q)
            return False
        if not isinstance(q["options"], list) or len(q["options"]) not in (2, 4):
            logger.warning("Attempt %d: Question %s has invalid options count: %d", attempt, q.get("id"), len(q.get("options", [])))
            return False
        if not isinstance(q["answer_index"], int) or not (0 <= q["answer_index"] < len(q["options"])):
            logger.warning("Attempt %d: Question %s has invalid answer_index", attempt, q.get("id"))
            return False
    return True


async def _generate_ollama(prompt: str, difficulty: str, num_questions: int) -> Optional[dict]:
    system_prompt = _build_system_prompt(difficulty, num_questions)
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": f"{system_prompt}\n\nUser Topic: {prompt}",
        "stream": False,
        "format": "json"
    }

    for attempt in range(1, config.LLM_MAX_RETRIES + 1):
        try:
            logger.info("Ollama attempt %d/%d for: '%s'", attempt, config.LLM_MAX_RETRIES, prompt[:100])
            response = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            quiz_data = json.loads(result['response'])
            if _validate_quiz(quiz_data, attempt):
                logger.info("Quiz generated via Ollama: '%s' with %d questions",
                            quiz_data.get("quiz_title", "Untitled"), len(quiz_data["questions"]))
                return quiz_data
        except requests.Timeout:
            logger.warning("Attempt %d: Ollama timed out after %ds", attempt, config.OLLAMA_TIMEOUT)
        except json.JSONDecodeError as e:
            logger.warning("Attempt %d: Failed to parse Ollama response as JSON: %s", attempt, e)
        except requests.RequestException as e:
            logger.error("Attempt %d: HTTP error calling Ollama: %s", attempt, e)
        except Exception as e:
            logger.error("Attempt %d: Unexpected error (Ollama): %s", attempt, e)

    return None


async def _generate_gemini(prompt: str, difficulty: str, num_questions: int) -> Optional[dict]:
    if not config.GEMINI_API_KEY:
        logger.error("Gemini API key not configured")
        return None

    system_prompt = _build_system_prompt(difficulty, num_questions)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Topic: {prompt}"}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.8,
        }
    }

    for attempt in range(1, config.LLM_MAX_RETRIES + 1):
        try:
            logger.info("Gemini attempt %d/%d for: '%s'", attempt, config.LLM_MAX_RETRIES, prompt[:100])
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            quiz_data = json.loads(text)
            if _validate_quiz(quiz_data, attempt):
                logger.info("Quiz generated via Gemini: '%s' with %d questions",
                            quiz_data.get("quiz_title", "Untitled"), len(quiz_data["questions"]))
                return quiz_data
        except json.JSONDecodeError as e:
            logger.warning("Attempt %d: Failed to parse Gemini response as JSON: %s", attempt, e)
        except requests.RequestException as e:
            logger.error("Attempt %d: HTTP error calling Gemini: %s", attempt, e)
        except (KeyError, IndexError) as e:
            logger.error("Attempt %d: Unexpected Gemini response structure: %s", attempt, e)
        except Exception as e:
            logger.error("Attempt %d: Unexpected error (Gemini): %s", attempt, e)

    return None


async def _generate_claude(prompt: str, difficulty: str, num_questions: int) -> Optional[dict]:
    if not config.ANTHROPIC_API_KEY:
        logger.error("Anthropic API key not configured")
        return None

    system_prompt = _build_system_prompt(difficulty, num_questions)
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": f"User Topic: {prompt}"}],
    }

    for attempt in range(1, config.LLM_MAX_RETRIES + 1):
        try:
            logger.info("Claude attempt %d/%d for: '%s'", attempt, config.LLM_MAX_RETRIES, prompt[:100])
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            result = response.json()
            text = result["content"][0]["text"]
            # Claude may wrap JSON in markdown code blocks
            if text.strip().startswith("```"):
                text = text.strip().split("\n", 1)[1].rsplit("```", 1)[0]
            quiz_data = json.loads(text)
            if _validate_quiz(quiz_data, attempt):
                logger.info("Quiz generated via Claude: '%s' with %d questions",
                            quiz_data.get("quiz_title", "Untitled"), len(quiz_data["questions"]))
                return quiz_data
        except json.JSONDecodeError as e:
            logger.warning("Attempt %d: Failed to parse Claude response as JSON: %s", attempt, e)
        except requests.RequestException as e:
            logger.error("Attempt %d: HTTP error calling Claude: %s", attempt, e)
        except (KeyError, IndexError) as e:
            logger.error("Attempt %d: Unexpected Claude response structure: %s", attempt, e)
        except Exception as e:
            logger.error("Attempt %d: Unexpected error (Claude): %s", attempt, e)

    return None


PROVIDERS = {
    "ollama": _generate_ollama,
    "gemini": _generate_gemini,
    "claude": _generate_claude,
}


class QuizEngine:
    def __init__(self):
        pass

    async def generate_quiz(self, prompt: str, difficulty: str = "medium",
                            num_questions: int = config.DEFAULT_NUM_QUESTIONS,
                            provider: str = "") -> Optional[dict]:
        provider = provider or config.DEFAULT_PROVIDER
        gen_fn = PROVIDERS.get(provider)
        if not gen_fn:
            logger.error("Unknown provider: %s", provider)
            return None

        logger.info("Generating quiz with provider '%s' for prompt: '%s'", provider, prompt[:100])
        result = await gen_fn(prompt, difficulty, num_questions)
        if not result:
            logger.error("Provider '%s' failed to generate quiz for: '%s'", provider, prompt[:100])
        return result

    def get_available_providers(self) -> list[dict]:
        providers = []
        # Ollama is always listed (local)
        providers.append({
            "id": "ollama",
            "name": "Ollama (Local)",
            "description": f"Local LLM via Ollama ({config.OLLAMA_MODEL})",
            "available": True,
        })
        providers.append({
            "id": "gemini",
            "name": "Gemini Flash",
            "description": f"Google Gemini ({config.GEMINI_MODEL})",
            "available": bool(config.GEMINI_API_KEY),
        })
        providers.append({
            "id": "claude",
            "name": "Claude",
            "description": f"Anthropic Claude ({config.ANTHROPIC_MODEL})",
            "available": bool(config.ANTHROPIC_API_KEY),
        })
        return providers


quiz_engine = QuizEngine()
