# backend/vibe-secure-gen/stages/llm_fix.py

"""
LLM-based vulnerability fixing for issues that Semgrep cannot auto-fix.
"""

from typing import Dict, Any, List
from .llm import stream_code
from .semgrep_smart_fix import run_semgrep_smart_fix

LLM_FIX_SYSTEM_PROMPT = """You are a security expert specializing in fixing code vulnerabilities.

CRITICAL INSTRUCTIONS:
1. Fix ALL security vulnerabilities listed below
2. Preserve ALL existing functionality - only change what's needed for security
3. Maintain the original code style, formatting, and structure
4. Return EXACTLY ONE fenced code block with the complete fixed code
5. If multi-file: use ```txt fence with '=== FILE: path ===' separators
6. If single-file: use appropriate language fence (```java, ```python, etc.)
7. NO explanations, NO comments about changes - ONLY the fixed code
8. Generate COMPLETE code - never truncate or use placeholders like "... rest of code ..."

ABSOLUTELY FORBIDDEN:
- Do NOT add comments explaining what you changed
- Do NOT write "// Fixed: XYZ" comments
- Do NOT include any text before or after the code fence
- Do NOT truncate any part of the code
"""


async def fix_with_llm(
    current_code: str,
    findings: List[Dict[str, Any]],
    max_attempts: int = 2
) -> Dict[str, Any]:
    """
    Use LLM to fix security vulnerabilities that Semgrep cannot auto-fix.
    
    Args:
        current_code: The code to fix (may already have Semgrep fixes applied)
        findings: List of security findings to fix
        max_attempts: Number of LLM fix attempts if first try doesn't work
    
    Returns:
        {
            "fixed": bool,
            "code": str,
            "issues_before": int,
            "issues_after": int,
            "fixes_applied": int,
            "attempt": int,
            "error": str (if failed)
        }
    """
    
    if not findings or len(findings) == 0:
        return {
            "fixed": False,
            "code": current_code,
            "issues_before": 0,
            "issues_after": 0,
            "fixes_applied": 0,
            "error": "No findings to fix"
        }
    
    # Format findings for LLM
    findings_text = _format_findings_detailed(findings)
    
    for attempt in range(1, max_attempts + 1):
        print(f"  🤖 LLM fix attempt {attempt}/{max_attempts}...")
        
        # Build fix prompt
        fix_prompt = f"""{LLM_FIX_SYSTEM_PROMPT}

SECURITY VULNERABILITIES TO FIX ({len(findings)} total):

{findings_text}

CURRENT CODE TO FIX:
{current_code}

Remember: Return ONLY the complete fixed code in a fenced block. No explanations."""
        
        try:
            # Generate fix with LLM
            parts = []
            async for chunk in stream_code(fix_prompt):
                if chunk:
                    parts.append(chunk)
            
            fixed_code = "".join(parts).strip()
            
            # Basic validation
            if not fixed_code or len(fixed_code) < 50:
                print(f"     ⚠️ LLM returned too little code ({len(fixed_code)} chars)")
                continue
            
            # Check if code was actually changed
            if fixed_code.strip() == current_code.strip():
                print(f"     ⚠️ LLM returned unchanged code")
                continue
            
            # Verify fix with Semgrep
            print(f"     🔍 Verifying LLM fixes...")
            verification = run_semgrep_smart_fix(fixed_code)
            
            if not verification.get("ok"):
                print(f"     ⚠️ Verification scan failed: {verification.get('error')}")
                continue
            
            issues_after = verification.get("findings_after", len(findings))
            fixes_applied = len(findings) - issues_after
            
            # Consider it successful if we reduced issues
            if fixes_applied > 0:
                print(f"     ✔ LLM fixed {fixes_applied} of {len(findings)} issues")
                return {
                    "fixed": True,
                    "code": fixed_code,
                    "issues_before": len(findings),
                    "issues_after": issues_after,
                    "fixes_applied": fixes_applied,
                    "attempt": attempt,
                    "verification_result": verification
                }
            else:
                print(f"     ⚠️ LLM changes didn't reduce issues")
                # Continue to next attempt
        
        except Exception as e:
            print(f"     ❌ LLM fix error: {type(e).__name__}: {e}")
            # Continue to next attempt
    
    # All attempts failed
    return {
        "fixed": False,
        "code": current_code,
        "issues_before": len(findings),
        "issues_after": len(findings),
        "fixes_applied": 0,
        "error": f"Failed after {max_attempts} attempts"
    }


def _format_findings_detailed(findings: List[Dict]) -> str:
    """Format findings with maximum detail for LLM comprehension."""
    parts = []
    
    for i, finding in enumerate(findings, 1):
        parts.append(f"{'='*60}")
        parts.append(f"VULNERABILITY #{i}")
        parts.append(f"{'='*60}")
        parts.append(f"Rule ID: {finding.get('check_id', 'unknown')}")
        parts.append(f"Severity: {finding.get('severity', 'UNKNOWN')}")
        parts.append(f"File: {finding.get('path', 'unknown')}")
        parts.append(f"Line: {finding.get('start', {}).get('line', '?')}")
        parts.append(f"")
        parts.append(f"Description:")
        parts.append(f"{finding.get('message', 'No description')}")
        
        # Add security context
        metadata = finding.get("metadata", {})
        if metadata:
            parts.append(f"")
            parts.append(f"Security Context:")
            if metadata.get("owasp"):
                parts.append(f"  - OWASP Category: {metadata['owasp']}")
            if metadata.get("cwe"):
                parts.append(f"  - CWE: {metadata['cwe']}")
            if metadata.get("category"):
                parts.append(f"  - Category: {metadata['category']}")
        
        parts.append(f"")
    
    return "\n".join(parts)