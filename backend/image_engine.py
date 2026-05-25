import httpx
import base64
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class ImageEngine:
    def __init__(self):
        self.api_url = config.SD_API_URL
        self.default_params = {
            "num_inference_steps": 20,
            "width": 768,
            "height": 432,
            "guidance_scale": 7.5,
            "negative_prompt": "text, watermark, logo, low quality, blurry, distorted, ugly"
        }

    async def is_available(self) -> bool:
        """Check if the configured image generation provider is available."""
        if config.IMAGE_GENERATION_PROVIDER == "gemini":
            return bool(config.GEMINI_API_KEY and config.GEMINI_IMAGE_MODEL)
        if config.IMAGE_GENERATION_PROVIDER in {"", "none", "disabled"}:
            return False

        """Check if local Image Gen server is running"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_url}/health", timeout=2)
                return response.status_code == 200 and response.json().get("model_loaded", False)
        except Exception:
            return False

    async def generate_image(self, prompt: str, style: str = "vibrant") -> Optional[str]:
        if config.IMAGE_GENERATION_PROVIDER == "gemini":
            return await self._generate_gemini_image(prompt, style=style)
        if config.IMAGE_GENERATION_PROVIDER in {"", "none", "disabled"}:
            return None
        return await self._generate_stable_diffusion_image(prompt, style=style)

    async def _generate_gemini_image(self, prompt: str, style: str = "vibrant") -> Optional[str]:
        """Generate an image using Gemini Flash Image. Returns base64 image data."""
        if not config.GEMINI_API_KEY or not config.GEMINI_IMAGE_MODEL:
            logger.warning("Gemini image generation requested without GEMINI_API_KEY/GEMINI_IMAGE_MODEL")
            return None

        style_prompts = {
            "vibrant": "vibrant, playful, party-game friendly digital illustration",
            "neon": "neon glow, high contrast, futuristic party-game artwork",
            "realistic": "clean realistic photo style, sharp focus, family-friendly",
        }
        enhanced_prompt = (
            f"Create a family-friendly quiz question image. {prompt}. "
            f"Style: {style_prompts.get(style, style_prompts['vibrant'])}. "
            "No text, labels, logos, watermarks, or UI elements."
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_IMAGE_MODEL}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": enhanced_prompt}]}],
            "generationConfig": {
                "responseModalities": ["Image"],
            },
        }
        headers = {"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=120)
                response.raise_for_status()
            result = response.json()
            parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            for part in parts:
                inline_data = part.get("inlineData") or part.get("inline_data") or {}
                image_b64 = inline_data.get("data")
                if not image_b64:
                    continue
                try:
                    raw = base64.b64decode(image_b64, validate=True)
                except Exception:
                    logger.warning("Invalid base64 in Gemini image response")
                    return None
                if len(raw) > config.MAX_IMAGE_SIZE_BYTES:
                    logger.warning("Gemini image too large (%d bytes), rejecting", len(raw))
                    return None
                return image_b64
            logger.warning("Gemini image response did not include inline image data")
            return None
        except Exception as e:
            logger.error("Gemini image generation error: %s", e)
            return None

    async def _generate_stable_diffusion_image(self, prompt: str, style: str = "vibrant") -> Optional[str]:
        """
        Generate an image using the local SD server.
        Returns base64-encoded image or None if generation fails.
        """
        style_prompts = {
            "vibrant": "vibrant colors, digital art, cinematic lighting, 8k resolution, highly detailed",
            "neon": "neon glow, dark background, glowing lines, futuristic, cyberpunk style",
            "realistic": "photorealistic, sharp focus, 8k, professional photography",
        }

        enhanced_prompt = f"{prompt}, {style_prompts.get(style, style_prompts['vibrant'])}"

        payload = {
            "prompt": enhanced_prompt,
            "negative_prompt": self.default_params["negative_prompt"],
            "num_inference_steps": self.default_params["num_inference_steps"],
            "width": self.default_params["width"],
            "height": self.default_params["height"],
            "guidance_scale": self.default_params["guidance_scale"],
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/generate",
                    json=payload,
                    timeout=120  # Image gen can take time on M1
                )
                result = response.json() if response.status_code == 200 else None

            if result:
                if "image_base64" in result:
                    image_b64 = result["image_base64"]
                    try:
                        raw = base64.b64decode(image_b64, validate=True)
                    except Exception:
                        logger.warning("Invalid base64 in image response")
                        return None
                    if len(raw) > config.MAX_IMAGE_SIZE_BYTES:
                        logger.warning("Image too large (%d bytes), rejecting", len(raw))
                        return None
                    return image_b64

            return None
        except Exception as e:
            logger.error("Image generation error: %s", e)
            return None

    async def generate_quiz_images(self, questions: list) -> dict:
        """
        Generate images for all questions in a quiz.
        Returns dict mapping question_id to base64 image.
        """
        images = {}

        if not await self.is_available():
            logger.warning("Image Gen server not available")
            return images

        for question in questions:
            if "image_prompt" in question and question["image_prompt"]:
                style = "vibrant"
                image = await self.generate_image(question["image_prompt"], style=style)
                if image:
                    images[question["id"]] = image

        return images


# Singleton instance
image_engine = ImageEngine()
