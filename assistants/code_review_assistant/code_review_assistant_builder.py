"""
Builder for the Code Review Assistant.
"""
from typing import Any, Optional
from langchain.prompts import PromptTemplate

from assistants.assistant_builder import AssistantBuilder
from assistants.logger import get_logger
from assistants.utils import get_provider

from .code_review_assistant import CodeReviewAssistant
from .tools import (
    analyze_code, 
    check_pep8, 
    analyze_complexity, 
    check_security, 
    suggest_best_practices,
    get_documentation_search_prompt
)

logger = get_logger()


class CodeReviewAssistantBuilder(AssistantBuilder):
    """Builder for creating an LLM-powered code review assistant.
    
    The assistant uses natural language understanding to select appropriate analysis tools
    and provides comprehensive, actionable code review feedback.
    """

    def __init__(
        self,
        raw_system_instructions: str = None,
        system_instruction_variables: Optional[dict] = None,
        tools: Optional[list] = None,
    ) -> None:
        if raw_system_instructions is None:
            raw_system_instructions = """You are an expert Python code review assistant powered by AI.

Your role is to help developers improve their code through intelligent analysis and actionable feedback.

When a user asks you to review code or asks questions about code quality, you should:

1. UNDERSTAND THE REQUEST: Analyze what the user is asking for
   - General code review? Use analyze_code, check_pep8, and suggest_best_practices
   - Security concerns? Use check_security
   - Performance or complexity issues? Use analyze_complexity
   - Looking for documentation? Use get_documentation_search_prompt

2. SELECT APPROPRIATE TOOLS: Choose tools based on the user's natural language query
   - Don't run all tools unless asked for comprehensive review
   - Be intelligent about which analysis is relevant

3. SYNTHESIZE RESULTS: Provide a clear, prioritized summary
   - Highlight critical issues first
   - Group related issues together
   - Provide specific, actionable suggestions
   - Explain WHY something is an issue, not just WHAT

4. BE HELPFUL: Act like a senior developer doing a code review
   - Use friendly, constructive language
   - Provide examples when helpful
   - Suggest documentation resources when relevant

Available tools:
- analyze_code: AST-based analysis for code structure, type hints, docstrings
- check_pep8: PEP 8 style compliance checking
- analyze_complexity: Cyclomatic complexity and nesting depth analysis
- check_security: Security vulnerability detection
- suggest_best_practices: Pythonic idioms and best practices
- get_documentation_search_prompt: Find relevant documentation

Remember: You're an intelligent agent, not a simple rule-based system. Use your judgment to provide the most valuable feedback based on what the user is asking for."""
        
        self.raw_system_instructions = raw_system_instructions
        self.system_instruction_variables = system_instruction_variables or {}
        self.tools = tools or []

    def register_default_tools(self):
        """Register all available code review tools"""
        if not self.tools:
            self.tools = [
                analyze_code,
                check_pep8,
                analyze_complexity,
                check_security,
                suggest_best_practices,
                get_documentation_search_prompt
            ]

    def render_prompt(self) -> str:
        # Use PromptTemplate to render template variables if any
        variables = list(self.system_instruction_variables.keys())
        prompt = PromptTemplate(
            input_variables=variables,
            template=self.raw_system_instructions,
            template_format="f-string",
        ).format(**self.system_instruction_variables) if variables else self.raw_system_instructions
        return prompt

    def build(self) -> CodeReviewAssistant:
        # Ensure default tools present
        self.register_default_tools()

        llm = get_provider()
        # If the LLM supports binding tools, bind them (safe-run)
        try:
            llm_with_tools = llm.bind_tools(self.tools)
        except Exception:
            logger.debug("LLM provider doesn't support bind_tools or failed; using raw llm")
            llm_with_tools = llm

        assistant = CodeReviewAssistant(
            llm=llm_with_tools,
            system_instructions=self.render_prompt(),
            tools=self.tools,
        )
        return assistant
