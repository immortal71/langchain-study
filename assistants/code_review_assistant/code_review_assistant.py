"""
Code Review Assistant implementation.

This Assistant extends the base `Assistant` class and uses an LLM agent to intelligently 
select and run appropriate analysis tools based on natural language queries.
"""
from typing import Any, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import BaseTool

from assistants.assistant import Assistant
from assistants.logger import get_logger

from .schemas import CodeReviewResponse, Issue
from .tools import (
    analyze_code, 
    check_pep8, 
    analyze_complexity, 
    check_security, 
    suggest_best_practices,
    get_documentation_search_prompt
)

logger = get_logger()


class CodeReviewAssistant(Assistant):
    """Assistant that reviews Python code using LLM-driven tool selection.
    
    The LLM acts as a central agent that:
    - Understands natural language queries about code
    - Selects appropriate analysis tools based on the request
    - Synthesizes tool outputs into actionable recommendations
    """

    def __init__(
        self,
        llm: Any = None,
        system_instructions: Optional[str] = None,
        tools: Optional[List[BaseTool]] = None,
        name: str = "code_review_assistant",
    ):
        super().__init__(name)

        self.llm = llm
        self.system_instructions = system_instructions
        self.tools = tools or []
        
        if self.system_instructions:
            try:
                self.add_message("system", self.system_instructions)
            except Exception:
                logger.debug("Failed to add system instructions to conversation history")

    def query(self, user_input: str) -> CodeReviewResponse:
        """Process natural language query using LLM agent to select and run appropriate tools.
        
        The LLM decides which tools to invoke based on the user's request, then synthesizes
        the results into a comprehensive code review.
        """
        self.add_message("user", user_input)

        issues: List[Issue] = []
        suggestions: List[str] = []
        review_summary = ""

        # If LLM is available, use it for intelligent tool selection
        if self.llm:
            try:
                # Create messages for LLM
                messages = [
                    SystemMessage(content=self.system_instructions or "You are a code review assistant."),
                    HumanMessage(content=user_input)
                ]
                
                # Let LLM decide and invoke tools
                response = self.llm.invoke(messages)
                
                # Process tool calls if LLM made any
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get('name', '')
                        tool_args = tool_call.get('args', {})
                        
                        # Execute the tool
                        tool_result = self._execute_tool(tool_name, tool_args)
                        if tool_result:
                            issues.extend(self._extract_issues(tool_result))
                            suggestions.extend(self._extract_suggestions(tool_result))
                    
                    # Get LLM's synthesis of results
                    synthesis_messages = messages + [
                        response,
                        HumanMessage(content=f"Based on the tool results, provide a comprehensive code review summary. Issues found: {len(issues)}")
                    ]
                    synthesis = self.llm.invoke(synthesis_messages)
                    review_summary = synthesis.content if hasattr(synthesis, 'content') else str(synthesis)
                else:
                    # LLM responded without tool calls - use content as summary
                    review_summary = response.content if hasattr(response, 'content') else str(response)
                    
            except Exception as e:
                logger.error(f"LLM processing failed: {e}")
                # Fallback to running all tools
                review_summary = "LLM analysis unavailable, running standard analysis."
                issues, suggestions = self._run_all_tools(user_input)
        else:
            # No LLM available - run all tools
            review_summary = "Running comprehensive static analysis."
            issues, suggestions = self._run_all_tools(user_input)

        # Calculate severity score
        severity_score = 0.0
        if issues:
            weight = {"low": 0.2, "medium": 0.5, "high": 1.0}
            severity_score = sum(weight.get(i.severity, 0.4) for i in issues) / len(issues)

        resp = CodeReviewResponse(
            review_summary=review_summary,
            issues_found=issues,
            suggestions=suggestions,
            severity_score=severity_score,
        )

        try:
            self.add_message("assistant", resp.json())
        except Exception:
            logger.debug("Failed to push assistant response to conversation history")
        
        return resp

    def _execute_tool(self, tool_name: str, tool_args: dict) -> Any:
        """Execute a specific tool by name with given arguments"""
        tool_map = {
            'analyze_code': analyze_code,
            'check_pep8': check_pep8,
            'analyze_complexity': analyze_complexity,
            'check_security': check_security,
            'suggest_best_practices': suggest_best_practices,
            'get_documentation_search_prompt': get_documentation_search_prompt
        }
        
        tool_func = tool_map.get(tool_name)
        if tool_func:
            try:
                return tool_func.invoke(tool_args)
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                return None
        return None

    def _extract_issues(self, tool_result: dict) -> List[Issue]:
        """Extract Issue objects from tool result"""
        issues = []
        for issue_data in tool_result.get('issues', []):
            if isinstance(issue_data, dict):
                issues.append(Issue(**issue_data))
        return issues

    def _extract_suggestions(self, tool_result: dict) -> List[str]:
        """Extract suggestion strings from tool result"""
        suggestions = []
        for item in tool_result.get('issues', []) + tool_result.get('suggestions', []):
            if isinstance(item, dict) and 'suggestion' in item:
                suggestions.append(item['suggestion'])
        return suggestions

    def _run_all_tools(self, code_snippet: str) -> tuple:
        """Fallback: run all available tools"""
        all_issues = []
        all_suggestions = []
        
        tools_to_run = [
            analyze_code,
            check_pep8,
            analyze_complexity,
            check_security,
            suggest_best_practices
        ]
        
        for tool_func in tools_to_run:
            try:
                result = tool_func.invoke({'code_snippet': code_snippet})
                all_issues.extend(self._extract_issues(result))
                all_suggestions.extend(self._extract_suggestions(result))
            except Exception as e:
                logger.error(f"Tool {tool_func.__name__} failed: {e}")
        
        return all_issues, all_suggestions
