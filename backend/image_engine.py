import requests
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

    def is_available(self) -> bool:
        """Check if local Image Gen server is running"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=2)
            return response.status_code == 200 and response.json().get("model_loaded", False)
        except Exception:
            return False

    async def generate_image(self, prompt: str, style: str = "vibrant") -> Optional[str]:
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
            response = requests.post(
                f"{self.api_url}/generate",
                json=payload,
                timeout=120  # Image gen can take time on M1
            )

            if response.status_code == 200:
                result = response.json()
                if "image_base64" in result:
                    image_b64 = result["image_base64"]
                    # Validate image size to prevent memory abuse
                    if len(image_b64) > config.MAX_IMAGE_SIZE_BYTES:
                        logger.warning("Image too large (%d bytes), rejecting", len(image_b64))
                        return None
                    # Validate it's actually valid base64
                    try:
                        base64.b64decode(image_b64, validate=True)
                    except Exception:
                        logger.warning("Invalid base64 in image response")
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

        if not self.is_available():
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
