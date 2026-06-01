# agents/llm_client.py
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

class LLMClient:
    def __init__(self, model_identifier="openrouter/free"):
        """
        Wraps the model call cleanly so providers/models can be swapped live 
        during the interview call without vendor-locking[cite: 69].
        """
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = model_identifier
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def generate_text(self, prompt: str) -> str:
        if not self.api_key:
            return "Error: OPENROUTER_API_KEY missing from .env file."
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Classroom Companion Bot"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            response = requests.post(self.url, headers=headers, json=payload)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
            else:
                return f"API Error: {response.status_code} | {response.text}"
        except Exception as e:
            return f"Network Connection Failed: {str(e)}"