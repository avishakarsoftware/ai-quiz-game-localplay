import requests
import base64
import os
from typing import Optional

# Local Apple Silicon Optimized SD Server
SD_API_URL = os.getenv("SD_API_URL", "http://localhost:8765")

class ImageEngine:
    def __init__(self):
        self.api_url = SD_API_URL
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
        except:
            return False
    
    async def generate_image(self, prompt: str, style: str = "vibrant") -> Optional[str]:
        """
        Generate an image using the local SD server.
        Returns base64-encoded image or None if generation fails.
        """
        # Enhance prompt based on the server's expectation (educational/vibrant)
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
                timeout=120 # Image gen can take time on M1
            )
            
            if response.status_code == 200:
                result = response.json()
                if "image_base64" in result:
                    return result["image_base64"]
            
            return None
        except Exception as e:
            print(f"Image generation error: {e}")
            return None
    
    async def generate_quiz_images(self, questions: list) -> dict:
        """
        Generate images for all questions in a quiz.
        Returns dict mapping question_id to base64 image.
        """
        images = {}
        
        if not self.is_available():
            print("Image Gen server not available")
            return images
        
        for question in questions:
            if "image_prompt" in question and question["image_prompt"]:
                # Use a specific style based on the prompt
                style = "vibrant"
                image = await self.generate_image(question["image_prompt"], style=style)
                if image:
                    images[question["id"]] = image
        
        return images


# Singleton instance
image_engine = ImageEngine()
