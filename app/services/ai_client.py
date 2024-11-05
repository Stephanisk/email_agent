from typing import Dict, Optional
from openai import OpenAI
from pydantic import BaseModel
import yaml
import os
from dotenv import load_dotenv

load_dotenv()

class AIResponse(BaseModel):
    content: str
    confidence: float
    requires_review: bool

class AIClient:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4')
        self.temperature = float(os.getenv('OPENAI_TEMPERATURE', 0.7))
        
        # Load hostel information
        with open('app/config/hostel_info.yaml', 'r') as file:
            self.hostel_info = yaml.safe_load(file)
    
    def _create_system_prompt(self) -> str:
        """Create the system prompt with hostel information."""
        return f"""You are an AI assistant for {self.hostel_info['hostel']['name']}. 
        Use the following information to respond to guest inquiries:
        
        {yaml.dump(self.hostel_info, default_flow_style=False)}
        
        Guidelines:
        1. Be friendly and professional
        2. Provide accurate information based on the hostel details
        3. If information is missing, acknowledge it and offer to find out
        4. Always include relevant policy information
        5. Format responses in a clear, easy-to-read manner
        """
    
    async def generate_response(self, 
                              email_content: str, 
                              email_metadata: Dict,
                              max_retries: int = 3) -> AIResponse:
        """Generate a response using GPT-4."""
        try:
            system_prompt = self._create_system_prompt()
            
            user_prompt = f"""
            Respond to this email inquiry:
            
            From: {email_metadata.get('from')}
            Subject: {email_metadata.get('subject')}
            Content: {email_content}
            
            Generate a professional response following the hostel's guidelines.
            """
            
            print("\n=== SENDING TO GPT-4 ===")
            print("System Prompt:", system_prompt)
            print("\nUser Prompt:", user_prompt)
            print("=" * 50)
            
            # Remove await since the new client is synchronous
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature
            )
            
            # Analyze confidence based on response
            requires_review = False
            confidence = 0.9  # Default high confidence
            
            response_content = response.choices[0].message.content
            
            print("\n=== GPT-4 RESPONSE ===")
            print(response_content)
            print("=" * 50)
            
            if "I'm not sure" in response_content.lower() or \
               "I would need to confirm" in response_content.lower():
                requires_review = True
                confidence = 0.6
            
            return AIResponse(
                content=response_content,
                confidence=confidence,
                requires_review=requires_review
            )
            
        except Exception as e:
            print(f"Error generating AI response: {str(e)}")
            raise