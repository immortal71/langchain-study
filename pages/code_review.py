"""
Streamlit page for the Code Review Assistant.

Provides a natural language interface for code review with intelligent tool selection.
"""
import streamlit as st
from assistants.code_review_assistant.code_review_assistant_builder import CodeReviewAssistantBuilder


def render_code_review_page():
    """Render the code review assistant page"""
    st.title("AI Code Review Assistant")
    st.markdown("""
    Get intelligent code review feedback powered by AI. Ask questions naturally:
    - "Can you review this code for security issues?"
    - "Check if this follows Python best practices"
    - "What's the complexity of this function?"
    - "Give me a comprehensive code review"
    """)
    
    # Initialize session state
    if 'code_review_history' not in st.session_state:
        st.session_state.code_review_history = []
    if 'assistant' not in st.session_state:
        try:
            builder = CodeReviewAssistantBuilder()
            st.session_state.assistant = builder.build()
        except Exception as e:
            st.error(f"Failed to initialize assistant: {e}")
            st.session_state.assistant = None
    
    # Code input section
    st.subheader("Code to Review")
    code_input = st.text_area(
        "Paste your Python code here",
        height=300,
        placeholder="def example():\n    pass",
        key="code_input"
    )
    
    # Query input section
    st.subheader("What would you like to know?")
    query_input = st.text_input(
        "Ask a question about the code",
        placeholder="Can you review this code for best practices?",
        key="query_input"
    )
    
    # Quick action buttons
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("Comprehensive Review"):
            query_input = f"Please provide a comprehensive code review for:\n{code_input}"
    
    with col2:
        if st.button("Security Check"):
            query_input = f"Check this code for security vulnerabilities:\n{code_input}"
    
    with col3:
        if st.button("Best Practices"):
            query_input = f"Review this code for Python best practices:\n{code_input}"
    
    with col4:
        if st.button("Complexity Analysis"):
            query_input = f"Analyze the complexity of this code:\n{code_input}"
    
    # Submit button
    if st.button("Review Code", type="primary"):
        if not code_input.strip():
            st.warning("Please paste some code to review")
        elif not query_input.strip():
            st.warning("Please ask a question or select a quick action")
        elif st.session_state.assistant is None:
            st.error("Assistant not initialized. Please check configuration.")
        else:
            with st.spinner("Analyzing code..."):
                try:
                    # Combine query with code
                    full_query = f"{query_input}\n\nCode:\n```python\n{code_input}\n```"
                    
                    # Get review
                    response = st.session_state.assistant.query(full_query)
                    
                    # Add to history
                    st.session_state.code_review_history.append({
                        'query': query_input,
                        'code': code_input,
                        'response': response
                    })
                    
                    # Display results
                    st.success("Review complete!")
                    
                    # Review Summary
                    st.subheader("Review Summary")
                    st.markdown(response.review_summary)
                    
                    # Severity Score
                    severity_color = "red" if response.severity_score > 0.7 else "orange" if response.severity_score > 0.4 else "green"
                    st.metric("Severity Score", f"{response.severity_score:.2f}", help="0.0 = no issues, 1.0 = critical issues")
                    
                    # Issues Found
                    if response.issues_found:
                        st.subheader(f"Issues Found ({len(response.issues_found)})")
                        
                        # Group by severity
                        high_issues = [i for i in response.issues_found if i.severity == "high"]
                        medium_issues = [i for i in response.issues_found if i.severity == "medium"]
                        low_issues = [i for i in response.issues_found if i.severity == "low"]
                        
                        if high_issues:
                            st.error(f"**High Priority ({len(high_issues)})**")
                            for issue in high_issues:
                                with st.expander(f"Line {issue.line_no}: {issue.message}"):
                                    st.write(f"**Suggestion:** {issue.suggestion}")
                        
                        if medium_issues:
                            st.warning(f"**Medium Priority ({len(medium_issues)})**")
                            for issue in medium_issues:
                                with st.expander(f"Line {issue.line_no}: {issue.message}"):
                                    st.write(f"**Suggestion:** {issue.suggestion}")
                        
                        if low_issues:
                            st.info(f"**Low Priority ({len(low_issues)})**")
                            for issue in low_issues:
                                with st.expander(f"Line {issue.line_no}: {issue.message}"):
                                    st.write(f"**Suggestion:** {issue.suggestion}")
                    else:
                        st.success("No issues found!")
                    
                    # Suggestions
                    if response.suggestions:
                        st.subheader("Key Suggestions")
                        for i, suggestion in enumerate(response.suggestions[:5], 1):
                            st.markdown(f"{i}. {suggestion}")
                    
                except Exception as e:
                    st.error(f"Error during review: {e}")
                    import traceback
                    st.code(traceback.format_exc())
    
    # Review History
    if st.session_state.code_review_history:
        st.divider()
        st.subheader("Review History")
        
        for i, review in enumerate(reversed(st.session_state.code_review_history[-5:]), 1):
            with st.expander(f"Review {len(st.session_state.code_review_history) - i + 1}: {review['query'][:50]}..."):
                st.code(review['code'][:200] + "..." if len(review['code']) > 200 else review['code'], language="python")
                st.write(f"**Issues:** {len(review['response'].issues_found)}")
                st.write(f"**Severity:** {review['response'].severity_score:.2f}")
    
    # Clear history button
    if st.session_state.code_review_history:
        if st.button("Clear History"):
            st.session_state.code_review_history = []
            st.rerun()


if __name__ == "__main__":
    render_code_review_page()
