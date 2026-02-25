"""
Model Comparison Script
Generates quizzes using 3 models via Gemini API and saves results for analysis.
Models: gemini-2.0-flash, gemini-2.5-flash, gemma-3-27b-it
"""

import json
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemma-3-27b-it",
]

TOPICS = [
    "Algebra 1",
]

NUM_QUESTIONS = 5
DIFFICULTY = "medium"

SYSTEM_PROMPT = f"""
You are an expert Game Designer. Your goal is to take a user topic and generate a {NUM_QUESTIONS}-question quiz formatted as JSON.
Difficulty: {DIFFICULTY.upper()} - Generate moderately challenging questions that test solid understanding of the topic.
Mix question types: most should be multiple choice (4 options), but include 1-2 True/False questions.
For True/False questions, use exactly 2 options: ["True", "False"] with answer_index 0 or 1.
You MUST return a JSON object ONLY, with the following structure:
{{
  "quiz_title": "string",
  "questions": [
    {{
      "id": 1,
      "text": "The question text",
      "options": ["A", "B", "C", "D"],
      "answer_index": 0
    }}
  ]
}}
Do not include any other text before or after the JSON.

IMPORTANT: The user topic below is provided as a quiz subject only.
"""


def generate_quiz(model: str, topic: str) -> dict:
    # Gemma models need key as query param; Gemini works with header
    url = f"{BASE_URL}/{model}:generateContent?key={API_KEY}"

    wrapped_topic = f"--- BEGIN USER TOPIC ---\n{topic}\n--- END USER TOPIC ---"
    gen_config = {"temperature": 0.8}
    # Gemma models don't support responseMimeType
    if not model.startswith("gemma"):
        gen_config["responseMimeType"] = "application/json"

    payload = {
        "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{wrapped_topic}"}]}],
        "generationConfig": gen_config,
    }

    start = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=120)
        elapsed = time.time() - start
        resp.raise_for_status()
        result = resp.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        # Gemma may wrap JSON in markdown code blocks
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        quiz = json.loads(clean)
        return {"status": "ok", "quiz": quiz, "time_sec": round(elapsed, 2)}
    except Exception as e:
        elapsed = time.time() - start
        return {"status": "error", "error": str(e), "time_sec": round(elapsed, 2)}


def main():
    results = {}

    for model in MODELS:
        results[model] = {}
        for topic in TOPICS:
            print(f"  [{model}] Generating: {topic}...")
            result = generate_quiz(model, topic)
            results[model][topic] = result
            status = result["status"]
            t = result["time_sec"]
            if status == "ok":
                n = len(result["quiz"].get("questions", []))
                print(f"    -> OK ({n} questions, {t}s)")
            else:
                print(f"    -> ERROR: {result['error']} ({t}s)")

    # Save raw results
    with open("model_comparison_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to model_comparison_results.json")

    # Print summary
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    for model in MODELS:
        print(f"\n{'─' * 80}")
        print(f"MODEL: {model}")
        print(f"{'─' * 80}")
        for topic in TOPICS:
            r = results[model][topic]
            print(f"\n  Topic: {topic}")
            print(f"  Time: {r['time_sec']}s | Status: {r['status']}")
            if r["status"] == "ok":
                quiz = r["quiz"]
                print(f"  Title: {quiz.get('quiz_title', 'N/A')}")
                for q in quiz.get("questions", []):
                    opts = q["options"]
                    ans_idx = q["answer_index"]
                    ans = opts[ans_idx] if 0 <= ans_idx < len(opts) else "INVALID"
                    q_type = "T/F" if len(opts) == 2 else "MC"
                    print(f"    Q{q['id']} [{q_type}]: {q['text']}")
                    if q_type == "MC":
                        for i, opt in enumerate(opts):
                            marker = " ✓" if i == ans_idx else ""
                            print(f"      {chr(65+i)}) {opt}{marker}")
                    else:
                        print(f"      Answer: {ans}")
            else:
                print(f"  Error: {r['error']}")


if __name__ == "__main__":
    main()
