import os
import json
from typing import Optional, List
import requests
import logging

logger = logging.getLogger(__name__)

class SchoolAIService:
    """
    AI service for generating questions from learning materials using GPT-3.5
    Named as "{school_name} AI" for personalization
    """
    
    def __init__(self, school_name: str = ""):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = "gpt-3.5-turbo"
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.school_name = school_name
        self.ai_name = f"{school_name} AI" if school_name else "SchoolAI"
    
    def generate_questions(
        self, 
        material_content: str = "", 
        num_questions: int = 5,
        question_type: str = "multiple_choice",
        difficulty: str = "medium",
        subject: str = "",
        is_topic: bool = False
    ) -> Optional[dict]:
        """
        Generate exam questions from learning material or topic using GPT-3.5
        
        Args:
            material_content: The text content of the learning material or topic description
            num_questions: Number of questions to generate (default 5)
            question_type: Type of questions - multiple_choice, short_answer, essay
            difficulty: Difficulty level - easy, medium, hard
            subject: Subject name for context
            is_topic: Whether this is a direct topic inquiry (True) or from a document (False)
        
        Returns:
            Dictionary with generated questions or None if failed
        """
        if not material_content or not material_content.strip():
            return {"error": "Please provide topic or material content"}
        
        if not self.api_key:
            logger.error("OpenAI API key not configured")
            return {"error": "AI service not configured. Please add OPENAI_API_KEY"}
        
        # Prepare the prompt
        prompt = self._build_prompt(
            material_content,
            num_questions,
            question_type,
            difficulty,
            subject,
            is_topic
        )
        
        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You are {self.ai_name}, an expert educational AI assistant. Generate {question_type} questions based on the provided learning material. Return the response as valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                return {"error": f"API error: {response.status_code}"}
            
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Parse the JSON response
            try:
                questions_data = json.loads(content)
                return {
                    "success": True,
                    "ai_name": self.ai_name,
                    "questions": questions_data,
                    "count": len(questions_data.get("questions", []))
                }
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from AI response, returning raw content")
                return {
                    "success": True,
                    "ai_name": self.ai_name,
                    "content": content,
                    "raw_response": True
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to OpenAI API failed: {str(e)}")
            return {"error": f"Failed to connect to AI service: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error in question generation: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}
    
    def _build_prompt(
        self,
        material_content: str,
        num_questions: int,
        question_type: str,
        difficulty: str,
        subject: str,
        is_topic: bool = False
    ) -> str:
        """Build the prompt for GPT-3.5"""
        
        subject_context = f" for {subject}" if subject else ""
        material_label = "Topic" if is_topic else "Learning Material"
        
        prompts = {
            "multiple_choice": f"""
Based on the following {material_label.lower()}, generate exactly {num_questions} multiple-choice questions{subject_context} at {difficulty} difficulty level.

{material_label}:
{material_content}

Requirements:
- Each question should have 4 options (A, B, C, D)
- Include the correct answer
- Ensure questions test understanding, not just memorization
- Return as JSON with this structure:
{{
    "questions": [
        {{
            "id": 1,
            "question": "Question text?",
            "options": ["A) Option A", "B) Option B", "C) Option C", "D) Option D"],
            "correct_answer": "A",
            "explanation": "Why this is correct..."
        }}
    ]
}}
""",
            "short_answer": f"""
Based on the following {material_label.lower()}, generate exactly {num_questions} short-answer questions{subject_context} at {difficulty} difficulty level.

{material_label}:
{material_content}

Requirements:
- Questions should require 1-3 sentence answers
- Include model answers and marking criteria
- Return as JSON with this structure:
{{
    "questions": [
        {{
            "id": 1,
            "question": "Question text?",
            "model_answer": "Expected answer...",
            "marking_points": ["Point 1", "Point 2", "Point 3"],
            "max_marks": 5
        }}
    ]
}}
""",
            "essay": f"""
Based on the following {material_label.lower()}, generate exactly {num_questions} essay questions{subject_context} at {difficulty} difficulty level.

{material_label}:
{material_content}

Requirements:
- Questions should encourage critical thinking and detailed responses
- Include marking rubrics
- Return as JSON with this structure:
{{
    "questions": [
        {{
            "id": 1,
            "question": "Essay question text?",
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "max_marks": 20,
            "rubric": {{
                "excellent": "18-20 marks: ...",
                "good": "14-17 marks: ...",
                "satisfactory": "10-13 marks: ...",
                "poor": "Below 10: ..."
            }}
        }}
    ]
}}
"""
        }
        
        return prompts.get(question_type, prompts["multiple_choice"])


def generate_school_ai_questions(
    school_name: str,
    material_content: str,
    is_topic: bool = False,
    **kwargs
) -> Optional[dict]:
    """
    Convenience function to generate questions with school-specific AI name
    
    Args:
        school_name: Name of the school for AI personalization
        material_content: The material or topic to generate questions from
        is_topic: Whether this is a direct topic inquiry (True) or from a document (False)
        **kwargs: Additional arguments (num_questions, question_type, difficulty, subject)
    """
    ai_service = SchoolAIService(school_name)
    return ai_service.generate_questions(material_content, is_topic=is_topic, **kwargs)
