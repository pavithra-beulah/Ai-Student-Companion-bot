# agents/orchestrator.py
import json
import re
from agents.llm_client import LLMClient

class AgentOrchestrator:
    def __init__(self):
        # Wraps the model call cleanly so providers can be swapped live
        self.client = LLMClient()

    def route_intent(self, text: str, role: str) -> str:
        """
        1. INTENT / ROUTING AGENT
        Classifies incoming user messages to determine the specific functional pipeline.
        """
        if role == 'teacher':
            prompt = f"""
            Analyze this message from a school teacher: "{text}"
            Classify its primary intent into exactly one of these categories:
            - 'ASSIGNMENT': If they are trying to assign new work or homework to a student.
            - 'QUERY': If they are asking a generic analytical question about how a student is doing.
            - 'OTHER': If it's a greeting or random text.
            
            Respond with ONLY the category string.
            """
            res = self.client.generate_text(prompt)
            
            # System logging check for debugging live incoming traffic on Render
            print(f"📡 Raw LLM Route Engine response text: {res}")
            
            if "ASSIGNMENT" in res: return "ASSIGNMENT"
            if "QUERY" in res: return "QUERY"
            return "OTHER"
        else:
            # Student messages are processed contextually as progress updates
            return "STUDENT_UPDATE"

    def teacher_agent_parse(self, text: str):
        """
        2. TEACHER AGENT
        Handles teacher assignment creation conversations. Extracts key metadata structures.
        """
        prompt = f"""
        You are the Teacher Agent. Analyze this text mapping out a student assignment:
        "{text}"
        
        Extract the values into a valid JSON object. Do not include markdown codeblocks or prose:
        {{
            "student_name": "Extract single student name mentioned, or null",
            "task": "Extract the description of the work assigned, or null",
            "deadline": "Extract the relative or absolute deadline duration, e.g., '3 days', 'Friday', or null"
        }}
        """
        raw_res = self.client.generate_text(prompt)
        
        # FIX: Safely isolate only the core JSON brackets {} to prevent parser crashes
        try:
            match = re.search(r"\{.*\}", raw_res, re.DOTALL)
            if match:
                cleaned = match.group(0).strip()
                return json.loads(cleaned)
            else:
                cleaned = re.sub(r"```json|```", "", raw_res).strip()
                return json.loads(cleaned)
        except Exception as parse_err:
            print(f"⚠️ JSON extraction parsing fallback caught: {parse_err}")
            return {"student_name": None, "task": text, "deadline": "Not specified"}

    def student_agent_classify(self, text: str) -> str:
        """
        3. STUDENT AGENT
        Interprets natural language student updates and converts them into system statuses.
        """
        prompt = f"""
        You are the Student Agent. Interpret this progress update message from a student:
        "{text}"
        
        Classify their status into exactly one string:
        - 'In Progress' (working on milestones, standard updates)
        - 'Stuck' (facing blockers, problems, confusion)
        - 'Completed' (stating they are completely done or submitting)
        
        Respond with ONLY the exact category name string: either 'In Progress', 'Stuck', or 'Completed'.
        """
        res = self.client.generate_text(prompt)
        if "Stuck" in res: return "Stuck"
        if "Completed" in res: return "Completed"
        return "In Progress"

    def summarizer_agent_global(self, assignments_list) -> str:
        """
        4. SUMMARIZER AGENT (Global Classroom Analytics)
        Compiles structural performance tracking summaries over all student lists.
        """
        if not assignments_list:
            return "📋 <b>No active student tracking records found in the database layer.</b>"
            
        formatted_data = ""
        for a in assignments_list:
            formatted_data += f"- Student: {a['student_name']} | Task: {a['task_description']} | Status: {a['status']} | Deadline: {a['deadline']}\n"
            
        prompt = f"""
        You are the Summariser Agent. Analyze this real-time data tracking list of student assignments:
        {formatted_data}
        
        Compile a punchy, professional summary update for the teacher.
        
        CRITICAL: Format your entire output using clean HTML tags ONLY. Do NOT use Markdown asterisks, backticks, or dashes.
        - Use <b>text</b> for bold headers or key student names.
        - Use <i>text</i> for assignment tasks.
        - Use <code>text</code> for statuses (e.g., <code>Stuck</code>).
        - Use standard structural spacing with newlines (\\n).
        
        Structure your text with:
        1. An overall 'Classroom Health' check.
        2. Direct actionable points highlighting students requiring immediate attention or review.
        """
        return self.client.generate_text(prompt)

    def summarizer_agent_single(self, student_username: str, query_text: str, assignments_list) -> str:
        """
        5. SUMMARIZER AGENT (Single Student Analytics)
        Fulfills contextual performance summary queries regarding specific students.
        """
        if not assignments_list:
            return f"📋 <b>No historical tracking data found for student @{student_username}.</b>"
            
        formatted_history = ""
        for a in assignments_list:
            formatted_history += f"- Task: {a['task_description']} | Status: {a['status']} | Deadline: {a['deadline']}\n"
            
        prompt = f"""
        You are the Summariser Agent. Provide a friendly status evaluation response answering this teacher query: "{query_text}"
        
        Here is the historical performance log for student '{student_username}':
        {formatted_history}
        
        CRITICAL: Format your entire output using clean HTML tags ONLY. Do NOT use Markdown asterisks, backticks, or dashes.
        - Use <b>text</b> for bold structures.
        - Use <i>text</i> for task descriptions.
        - Use <code>text</code> for exact status metrics (e.g., <code>In Progress</code>, <code>Stuck</code>).
        - Keep lines spaced neatly using standard newlines (\\n).
        
        Write an assessment answering the teacher's query. Evaluate if they are on track, call out specific statuses explicitly, and provide 1-2 points on how the teacher can assist them.
        """
        return self.client.generate_text(prompt)
