"""Utility functions for QA resolver"""
import re
import logging

def clean_text(text):
    """Clean text by removing extra whitespace, etc."""
    if not text:
        return ""
    
    # Replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    # Trim leading/trailing whitespace
    return text.strip()

def extract_text_from_node(node):
    """Extract text content from an XML node"""
    if not node:
        return ""
    
    text_parts = []
    for child in node.childNodes:
        if child.nodeType == child.TEXT_NODE:
            text_parts.append(child.data)
        elif child.nodeType == child.ELEMENT_NODE:
            text_parts.append(extract_text_from_node(child))
    
    return "".join(text_parts)

def log_error_details(unit, warning):
    """Log details about an error for debugging"""
    try:
        unit_id = unit.getAttribute('id') if unit else "unknown"
        warning_code = None
        warning_text = None
        
        if warning:
            for attr in warning.attributes.values():
                if 'code' in attr.name.lower():
                    warning_code = attr.value
                    break
            
            warning_text = extract_text_from_node(warning)
        
        logging.debug(f"Error details - Unit: {unit_id}, Code: {warning_code}")
        logging.debug(f"Warning text: {warning_text}")
    
    except Exception as e:
        logging.error(f"Error logging details: {str(e)}")