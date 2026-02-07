import requests
import json
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct") # Using available local model

class QuizEngine:
    def __init__(self):
        pass

    async def generate_quiz(self, prompt: str):
        system_prompt = """
        You are an expert Game Designer. Your goal is to take a user topic and generate a 10-question quiz formatted as JSON.
        You MUST return a JSON object ONLY, with the following structure:
        {
          "quiz_title": "string",
          "questions": [
            {
              "id": 1,
              "text": "The question text",
              "options": ["A", "B", "C", "D"],
              "answer_index": 0,
              "image_prompt": "A detailed descriptive prompt for an image generator that depicts the subject of this question."
            }
          ]
        }
        Do not include any other text before or after the JSON.
        """
        
        payload = {
            "model": MODEL_NAME,
            "prompt": f"{system_prompt}\n\nUser Topic: {prompt}",
            "stream": False,
            "format": "json"
        }
        
        try:
            response = requests.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            return json.loads(result['response'])
        except Exception as e:
            print(f"Error generating quiz: {e}")
            return None

quiz_engine = QuizEngine()
