"""AI Handler for MemoQ QA Error Resolution Tool"""
import logging
import os
import json
import time

# Check if we have API key for OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

try:
    from openai import OpenAI
    if OPENAI_API_KEY:
        # Create client with API key
        client = OpenAI(api_key=OPENAI_API_KEY)
        # Set organization if provided
        if os.environ.get("OPENAI_ORG_ID"):
            client.organization = os.environ.get("OPENAI_ORG_ID")
        HAS_OPENAI = True
    else:
        print("\n" + "=" * 80)
        print("WARNING: OpenAI API key not found in environment variables.")
        print("To enable AI features, set the OPENAI_API_KEY environment variable:")
        print("  In PowerShell: $env:OPENAI_API_KEY = 'your-api-key'")
        print("  Permanently: [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'your-api-key', 'User')")
        print("=" * 80 + "\n")
        HAS_OPENAI = False
except ImportError:
    HAS_OPENAI = False
    print("\n" + "=" * 80)
    print("WARNING: OpenAI package not installed. AI functions will not work.")
    print("Install with: pip install openai")
    print("=" * 80 + "\n")
    logging.warning("OpenAI package not installed. AI functions will not work.")

def evaluate_terminology(source_text, target_text, source_term, target_suggestions, model="gpt-4"):
    """Evaluate a terminology error and suggest a fix
    
    Args:
        source_text: The source segment text
        target_text: The target segment text
        source_term: The source term with the error
        target_suggestions: List of suggested target terms
        model: Which OpenAI model to use
        
    Returns:
        dict: Result with keys:
            - needs_fix (bool): Whether a fix is needed
            - new_text (str): The fixed text (if needed)
            - explanation (str): Explanation of the decision
    """
    if not HAS_OPENAI or not OPENAI_API_KEY:
        logging.warning("OpenAI not available. Using mock response for terminology evaluation.")
        # Mock response when OpenAI is not available
        return {
            'needs_fix': False,
            'new_text': target_text,
            'explanation': "OpenAI API not available. Please install the package and set OPENAI_API_KEY."
        }
    
    try:
        # Construct prompt
        prompt = f"""
You are a professional translator and terminology expert. You need to evaluate a terminology issue:

SOURCE TEXT: {source_text}
TARGET TEXT: {target_text}
SOURCE TERM: {source_term}
SUGGESTED TARGET TERMS: {', '.join(target_suggestions)}

The MemoQ CAT tool has flagged a terminology error. The source term appears in the source text, but none of 
the suggested target terms appear in the target text.

Please analyze:
1. Is the source term correctly translated in the target, just using different terminology?
2. Is there a mistake in the translation that needs to be fixed?
3. What is the best way to incorporate one of the suggested terms while maintaining naturalness?

Respond with JSON in this format:
{{
  "needs_fix": true/false,
  "new_text": "fixed text if needed",
  "explanation": "explanation of your decision"
}}
"""
        
        # Call OpenAI API using v1.0+ client
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional translator assisting with terminology issues."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )
        
        # Extract and parse response
        response_text = response.choices[0].message.content
        result = json.loads(response_text)
        
        # Validate result has required fields
        if 'needs_fix' not in result or 'new_text' not in result or 'explanation' not in result:
            raise ValueError("Invalid response format from OpenAI")
        
        logging.info(f"AI evaluation: needs_fix={result['needs_fix']}")
        logging.debug(f"AI explanation: {result['explanation']}")
        
        return result
    
    except Exception as e:
        logging.error(f"Error in AI evaluation: {str(e)}")
        # Fallback response
        return {
            'needs_fix': False,
            'new_text': target_text,
            'explanation': f"Error in AI evaluation: {str(e)}"
        }

def analyze_consistency(source_text, target_text, consistent_text, inconsistent_text, related_segments=None, model="gpt-4"):
    """Analyze consistency errors and suggest a fix
    
    Args:
        source_text: The source segment text
        target_text: The target segment text
        consistent_text: The consistent/expected text
        inconsistent_text: The inconsistent text (current)
        related_segments: List of related segment IDs
        model: Which OpenAI model to use
        
    Returns:
        dict: Result with keys:
            - needs_fix (bool): Whether a fix is needed
            - new_text (str): The fixed text (if needed)
            - explanation (str): Explanation of the decision
    """
    if not HAS_OPENAI or not OPENAI_API_KEY:
        logging.warning("OpenAI not available. Using mock response for consistency evaluation.")
        # Mock response when OpenAI is not available
        return {
            'needs_fix': False,
            'new_text': target_text,
            'explanation': "OpenAI API not available. Please install the package and set OPENAI_API_KEY."
        }
    
    try:
        # Construct prompt
        related_segments_text = "None" if not related_segments else ", ".join(related_segments)
        
        prompt = f"""
You are a professional translator and consistency expert. You need to evaluate a consistency issue:

SOURCE TEXT: {source_text}
TARGET TEXT: {target_text}
CONSISTENT TEXT: {consistent_text}
INCONSISTENT TEXT: {inconsistent_text}
RELATED SEGMENTS: {related_segments_text}

The MemoQ CAT tool has flagged a consistency error. The current translation uses the inconsistent text, 
but in previous similar segments, the consistent text was used.

Please analyze:
1. Is there actually a consistency issue, or is this a false positive?
2. If there is an issue, what would be the best way to fix the target text to maintain consistency?
3. Should the target text be updated to match the consistent text pattern?

Respond with JSON in this format:
{{
  "needs_fix": true/false,
  "new_text": "fixed text if needed",
  "explanation": "explanation of your decision"
}}
"""
        
        # Call OpenAI API using v1.0+ client
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional translator assisting with consistency issues."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )
        
        # Extract and parse response
        response_text = response.choices[0].message.content
        result = json.loads(response_text)
        
        # Validate result has required fields
        if 'needs_fix' not in result or 'new_text' not in result or 'explanation' not in result:
            raise ValueError("Invalid response format from OpenAI")
        
        logging.info(f"AI evaluation: needs_fix={result['needs_fix']}")
        logging.debug(f"AI explanation: {result['explanation']}")
        
        return result
    
    except Exception as e:
        logging.error(f"Error in AI evaluation: {str(e)}")
        # Fallback response
        return {
            'needs_fix': False,
            'new_text': target_text,
            'explanation': f"Error in AI evaluation: {str(e)}"
        }