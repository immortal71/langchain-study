"""
Tools for the code review assistant.
Provides comprehensive code analysis including AST analysis, PEP8 checking, 
complexity analysis, security checks, and best practices recommendations.
"""
from typing import Dict, Any, List
import ast
import re

# Try to import decorator from langchain_core, fallback if not available
try:
    from langchain_core.tools import tool  # pragma: no cover - optional dependency
except Exception:
    def tool(func):
        # Simple passthrough decorator to keep signature compatible
        return func


@tool
def analyze_code(code_snippet: str) -> Dict[str, Any]:
    """
    Analyze python code snippet for a set of simple static issues.

    Returns a dict with `issues` list where each item includes message, line_no, severity, suggestion.
    """
    issues: List[Dict[str, Any]] = []

    # Syntax check
    try:
        tree = ast.parse(code_snippet)
    except SyntaxError as se:
        issues.append({
            "message": f"Syntax error: {se.msg}",
            "line_no": se.lineno,
            "severity": "high",
            "suggestion": "Fix syntax error."}
        )
        return {"issues": issues}

    # Iterate through functions and top-level for analysis
    assign_zero_vars = set()

    for node in ast.walk(tree):
        # Check function definitions for docstrings and type hints
        if isinstance(node, ast.FunctionDef):
            doc = ast.get_docstring(node)
            if not doc:
                issues.append({
                    "message": f"Function '{node.name}' is missing a docstring.",
                    "line_no": node.lineno,
                    "severity": "medium",
                    "suggestion": "Add a docstring describing purpose, args, and return value."})

            # Check type hints
            missing_annotations = []
            for arg in node.args.args:
                if arg.arg == "self":
                    continue
                if arg.annotation is None:
                    missing_annotations.append(arg.arg)
            if node.returns is None:
                missing_annotations.append("return")
            if missing_annotations:
                issues.append({
                    "message": f"Function '{node.name}' is missing type hints for: {', '.join(missing_annotations)}.",
                    "line_no": node.lineno,
                    "severity": "medium",
                    "suggestion": "Add type hints to arguments and return value."})

        # Detect assignments to zero values to spot patterns
        if isinstance(node, ast.Assign):
            # Only track simple `total = 0` assignments (single target)
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if isinstance(node.value, ast.Constant) and node.value.value == 0:
                    assign_zero_vars.add(node.targets[0].id)

        # Detect for-loops that update a var via `var = var + x` or `var += x` (sum pattern)
        if isinstance(node, ast.For):
            # Walk the for body to find AugAssign or Assign patterns
            for inner in node.body:
                if isinstance(inner, ast.AugAssign):
                    if isinstance(inner.target, ast.Name) and inner.target.id in assign_zero_vars:
                        # Found a summation pattern
                        issues.append({
                            "message": f"Summation update to '{inner.target.id}' inside loop. Use `sum()` where appropriate.",
                            "line_no": inner.lineno,
                            "severity": "low",
                            "suggestion": "Use builtin `sum()` for readability and performance when suitable."})
                if isinstance(inner, ast.Assign):
                    if len(inner.targets) == 1 and isinstance(inner.targets[0], ast.Name):
                        name = inner.targets[0].id
                        # check if value is BinOp name + something
                        if isinstance(inner.value, ast.BinOp) and isinstance(inner.value.left, ast.Name):
                            if inner.value.left.id == name:
                                issues.append({
                                    "message": f"Pattern updating '{name}' using '{name} = {name} + ...' inside loop. Consider using `sum()`.",
                                    "line_no": inner.lineno,
                                    "severity": "low",
                                    "suggestion": "Use `sum()` or generator expressions instead of manual accumulation when suitable."})

        # Check variable names
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if len(node.id) < 3 and node.id.isalpha():
                issues.append({
                    "message": f"Short variable name '{node.id}'. Consider a more descriptive name.",
                    "line_no": node.lineno if hasattr(node, 'lineno') else None,
                    "severity": "low",
                    "suggestion": "Use descriptive variable names (>=3 characters) for readability."})

    # If issues list empty, provide a short summary
    if not issues:
        summary = "No obvious issues found."
    else:
        summary = f"Found {len(issues)} issue(s)."

    return {"issues": issues, "summary": summary}


@tool
def check_pep8(code_snippet: str) -> Dict[str, Any]:
    """
    Check for common PEP8 style violations.

    If `pycodestyle` (or `flake8`) is available it will use that to generate an output list. Otherwise, this function runs a few simple heuristics.
    """
    issues = []

    # Try to import pycodestyle
    try:
        import pycodestyle
    except Exception:
        pycodestyle = None

    # If pycodestyle is installed, use it
    if pycodestyle:
        style = pycodestyle.StyleGuide(quiet=True)
        # pycodestyle expects filenames, so write to a temporary file
        import tempfile
        import os

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py") as tf:
            tf.write(code_snippet)
            fname = tf.name
        try:
            report = style.check_files([fname])
            # pycodestyle doesn't expose issues as an API but it writes to the report object
            # Use the `report` object's `get_statistics()` to get lines
            for stat in report.get_statistics(''):
                # stat looks like "path:line:col: E123 message"
                # We'll just add the stat as low severity
                issues.append({"message": stat, "severity": "low"})
        finally:
            os.remove(fname)

    else:
        # Simple heuristics
        for i, line in enumerate(code_snippet.splitlines(), start=1):
            # Line length
            if len(line) > 79:
                issues.append({
                    "message": f"Line {i} exceeds 79 characters (len={len(line)}).",
                    "line_no": i,
                    "severity": "low",
                    "suggestion": "Wrap long lines or refactor to shorten them."})

            # Trailing whitespace
            if line.rstrip() != line:
                issues.append({
                    "message": f"Line {i} has trailing whitespace.",
                    "line_no": i,
                    "severity": "low",
                    "suggestion": "Remove trailing whitespace."})

            # Indentation
            if line.startswith('\t'):
                issues.append({
                    "message": f"Line {i} uses a TAB for indentation; prefer 4 spaces.",
                    "line_no": i,
                    "severity": "low",
                    "suggestion": "Replace tabs with 4 spaces for PEP 8 compliance."})

    severity_score = min(1.0, 0.1 * len(issues))
    return {"issues": issues, "severity_score": severity_score}


@tool
def analyze_complexity(code_snippet: str) -> Dict[str, Any]:
    """
    Analyze code complexity including cyclomatic complexity and nesting depth.
    
    Returns complexity metrics and recommendations for refactoring.
    """
    issues = []
    
    try:
        tree = ast.parse(code_snippet)
    except SyntaxError:
        return {"issues": [{"message": "Cannot analyze complexity due to syntax errors", "severity": "high"}]}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Calculate cyclomatic complexity (simplified)
            complexity = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                    complexity += 1
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1
            
            if complexity > 10:
                issues.append({
                    "message": f"Function '{node.name}' has high complexity ({complexity})",
                    "line_no": node.lineno,
                    "severity": "high",
                    "suggestion": "Consider breaking down into smaller functions. Target complexity < 10."
                })
            elif complexity > 5:
                issues.append({
                    "message": f"Function '{node.name}' has moderate complexity ({complexity})",
                    "line_no": node.lineno,
                    "severity": "medium",
                    "suggestion": "Consider refactoring for better maintainability."
                })
            
            # Check nesting depth
            max_depth = _calculate_nesting_depth(node)
            if max_depth > 4:
                issues.append({
                    "message": f"Function '{node.name}' has deep nesting (depth {max_depth})",
                    "line_no": node.lineno,
                    "severity": "medium",
                    "suggestion": "Reduce nesting by extracting functions or using early returns."
                })
    
    return {
        "issues": issues,
        "summary": f"Analyzed complexity: {len(issues)} issue(s) found"
    }


def _calculate_nesting_depth(node, depth=0):
    """Helper to calculate maximum nesting depth"""
    max_depth = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.With, ast.Try)):
            child_depth = _calculate_nesting_depth(child, depth + 1)
            max_depth = max(max_depth, child_depth)
    return max_depth


@tool
def check_security(code_snippet: str) -> Dict[str, Any]:
    """
    Check for common security issues and vulnerabilities.
    
    Detects patterns like eval, exec, SQL injection risks, hardcoded secrets, etc.
    """
    issues = []
    lines = code_snippet.splitlines()
    
    # Pattern matching for common security issues
    dangerous_functions = {
        'eval': 'Using eval() is dangerous and can execute arbitrary code',
        'exec': 'Using exec() can execute arbitrary code',
        'pickle': 'Pickle can execute arbitrary code during deserialization',
        '__import__': 'Dynamic imports can be security risks'
    }
    
    for i, line in enumerate(lines, 1):
        # Check for dangerous functions
        for func, msg in dangerous_functions.items():
            if re.search(rf'\b{func}\s*\(', line):
                issues.append({
                    "message": msg,
                    "line_no": i,
                    "severity": "high",
                    "suggestion": f"Avoid using {func}() or sanitize inputs thoroughly"
                })
        
        # Check for hardcoded passwords/secrets
        if re.search(r'(password|secret|api_key|token)\s*=\s*["\'][\w\-]+["\']', line, re.IGNORECASE):
            issues.append({
                "message": "Potential hardcoded secret detected",
                "line_no": i,
                "severity": "high",
                "suggestion": "Use environment variables or secret management systems"
            })
        
        # Check for SQL injection patterns
        if re.search(r'execute\s*\([^)]*["\'].*%s.*["\'][^)]*\)', line):
            issues.append({
                "message": "Potential SQL injection vulnerability",
                "line_no": i,
                "severity": "high",
                "suggestion": "Use parameterized queries instead of string formatting"
            })
        
        # Check for unsafe file operations
        if re.search(r'open\s*\([^)]*\+[^)]*["\'][wax]', line):
            issues.append({
                "message": "File opened in write mode without validation",
                "line_no": i,
                "severity": "medium",
                "suggestion": "Validate file paths to prevent directory traversal"
            })
    
    return {
        "issues": issues,
        "summary": f"Security scan: {len(issues)} issue(s) found"
    }


@tool
def suggest_best_practices(code_snippet: str) -> Dict[str, Any]:
    """
    Suggest Python best practices and idiomatic improvements.
    
    Provides recommendations for more Pythonic code.
    """
    suggestions = []
    
    try:
        tree = ast.parse(code_snippet)
    except SyntaxError:
        return {"suggestions": [], "summary": "Cannot analyze due to syntax errors"}
    
    for node in ast.walk(tree):
        # Suggest list comprehensions
        if isinstance(node, ast.For):
            has_append = any(
                isinstance(child, ast.Expr) and 
                isinstance(child.value, ast.Call) and
                isinstance(child.value.func, ast.Attribute) and
                child.value.func.attr == 'append'
                for child in node.body
            )
            if has_append and len(node.body) == 1:
                suggestions.append({
                    "message": "Consider using list comprehension",
                    "line_no": node.lineno,
                    "severity": "low",
                    "suggestion": "List comprehensions are more Pythonic and often faster"
                })
        
        # Check for exception handling best practices
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                suggestions.append({
                    "message": "Bare except clause catches all exceptions",
                    "line_no": node.lineno,
                    "severity": "medium",
                    "suggestion": "Catch specific exceptions instead of using bare except"
                })
            elif isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                suggestions.append({
                    "message": "Catching generic Exception is too broad",
                    "line_no": node.lineno,
                    "severity": "low",
                    "suggestion": "Catch more specific exception types when possible"
                })
        
        # Suggest context managers for file operations
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'open':
                # Check if it's within a 'with' statement
                parent_is_with = False
                # This is simplified; proper check would need parent tracking
                suggestions.append({
                    "message": "Consider using context manager for file operations",
                    "line_no": node.lineno,
                    "severity": "low",
                    "suggestion": "Use 'with open(...) as f:' to ensure proper resource cleanup"
                })
        
        # Check for mutable default arguments
        if isinstance(node, ast.FunctionDef):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    suggestions.append({
                        "message": f"Function '{node.name}' uses mutable default argument",
                        "line_no": node.lineno,
                        "severity": "high",
                        "suggestion": "Use None as default and initialize inside function to avoid shared state bugs"
                    })
    
    return {
        "suggestions": suggestions,
        "summary": f"Best practices review: {len(suggestions)} suggestion(s)"
    }


@tool
def get_documentation_search_prompt(query: str) -> Dict[str, Any]:
    """
    Generate a prompt for searching Python documentation or best practices.
    
    This tool helps construct search queries for finding relevant documentation.
    """
    search_topics = {
        "pep8": "Python PEP 8 Style Guide",
        "type hints": "Python Type Hints PEP 484",
        "async": "Python asyncio documentation",
        "testing": "Python unittest and pytest documentation",
        "security": "Python security best practices OWASP",
        "performance": "Python performance optimization techniques"
    }
    
    matched_topics = []
    query_lower = query.lower()
    
    for key, topic in search_topics.items():
        if key in query_lower:
            matched_topics.append(topic)
    
    if not matched_topics:
        matched_topics = ["Python official documentation"]
    
    return {
        "search_suggestions": matched_topics,
        "query": query,
        "summary": f"Recommended documentation: {', '.join(matched_topics)}"
    }
