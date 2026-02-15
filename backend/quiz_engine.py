import requests
import json
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class QuizEngine:
    def __init__(self):
        pass

    async def generate_quiz(self, prompt: str, difficulty: str = "medium",
                            num_questions: int = config.DEFAULT_NUM_QUESTIONS) -> Optional[dict]:
        difficulty_instructions = {
            "easy": "Generate simple, factual questions suitable for beginners. Keep language clear and answers obvious.",
            "medium": "Generate moderately challenging questions that test solid understanding of the topic.",
            "hard": "Generate challenging questions that test deep knowledge, nuance, and critical thinking.",
        }
        difficulty_text = difficulty_instructions.get(difficulty, difficulty_instructions["medium"])

        system_prompt = f"""
        You are an expert Game Designer. Your goal is to take a user topic and generate a {num_questions}-question quiz formatted as JSON.
        Difficulty: {difficulty.upper()} - {difficulty_text}
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

        payload = {
            "model": config.OLLAMA_MODEL,
            "prompt": f"{system_prompt}\n\nUser Topic: {prompt}",
            "stream": False,
            "format": "json"
        }

        for attempt in range(1, config.LLM_MAX_RETRIES + 1):
            try:
                logger.info("Generating quiz (attempt %d/%d) for prompt: '%s'", attempt, config.LLM_MAX_RETRIES, prompt[:100])
                response = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
                response.raise_for_status()
                result = response.json()
                quiz_data = json.loads(result['response'])

                # Validate structure
                if not isinstance(quiz_data, dict):
                    logger.warning("Attempt %d: LLM returned non-dict type: %s", attempt, type(quiz_data).__name__)
                    continue
                if "questions" not in quiz_data or not isinstance(quiz_data["questions"], list):
                    logger.warning("Attempt %d: Missing or invalid 'questions' field", attempt)
                    continue
                if len(quiz_data["questions"]) == 0:
                    logger.warning("Attempt %d: Empty questions list", attempt)
                    continue

                # Validate each question has required fields
                valid = True
                for q in quiz_data["questions"]:
                    if not all(k in q for k in ("id", "text", "options", "answer_index")):
                        logger.warning("Attempt %d: Question missing required fields: %s", attempt, q)
                        valid = False
                        break
                    if not isinstance(q["options"], list) or len(q["options"]) not in (2, 4):
                        logger.warning("Attempt %d: Question %s has invalid options count: %d", attempt, q.get("id"), len(q.get("options", [])))
                        valid = False
                        break
                    if not isinstance(q["answer_index"], int) or not (0 <= q["answer_index"] < len(q["options"])):
                        logger.warning("Attempt %d: Question %s has invalid answer_index", attempt, q.get("id"))
                        valid = False
                        break

                if not valid:
                    continue

                logger.info("Quiz generated successfully: '%s' with %d questions",
                            quiz_data.get("quiz_title", "Untitled"), len(quiz_data["questions"]))
                return quiz_data

            except requests.Timeout:
                logger.warning("Attempt %d: Ollama request timed out after %ds", attempt, config.OLLAMA_TIMEOUT)
            except json.JSONDecodeError as e:
                logger.warning("Attempt %d: Failed to parse LLM response as JSON: %s", attempt, e)
            except requests.RequestException as e:
                logger.error("Attempt %d: HTTP error calling Ollama: %s", attempt, e)
            except Exception as e:
                logger.error("Attempt %d: Unexpected error generating quiz: %s", attempt, e)

        logger.error("All %d attempts to generate quiz failed for prompt: '%s'", config.LLM_MAX_RETRIES, prompt[:100])
        return None


quiz_engine = QuizEngine()
