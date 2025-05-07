"""MemoQ Terminology Error Resolver Module"""
import logging
import re
from xml.dom import minidom
from common import ai_handler, utils

def process(mqxliff_dom, auto_mode=False, model="gpt-4", debug=False):
    """Process terminology errors (code 03091) in the MQXLIFF file
    
    Args:
        mqxliff_dom: The parsed MQXLIFF DOM
        auto_mode: Whether to run in automatic mode
        model: The OpenAI model to use
        debug: Whether to enable debug logging
        
    Returns:
        dict: Statistics about the processing
    """
    stats = {'fixed': 0, 'ignored': 0, 'total': 0}
    
    # Find all terminology errors
    terminology_errors = find_terminology_errors(mqxliff_dom, debug)
    stats['total'] = len(terminology_errors)
    
    logging.info(f"Found {stats['total']} terminology errors")
    
    # Process each error
    for i, (unit, warning, error_info) in enumerate(terminology_errors):
        # Extract context
        unit_id = unit.getAttribute('id')
        source_text, target_text = extract_source_target(unit)
        
        # Use the error_info from detection if available, otherwise try to extract it
        term_info = error_info if error_info else extract_term_info(warning)
        
        logging.info(f"Processing terminology error {i+1}/{stats['total']} in unit {unit_id}")
        if debug:
            logging.debug(f"Source text: {source_text}")
            logging.debug(f"Target text: {target_text}")
            
        logging.info(f"Source term: {term_info.get('source_term', 'unknown')}, Target suggestions: {term_info.get('target_suggestions', [])}")
        
        # Skip if term already present (unless forced by debug mode)
        if not debug and is_term_present(term_info.get('target_suggestions', []), target_text):
            logging.info("Term already present in target, marking as ignored")
            if mark_as_ignored(warning):
                stats['ignored'] += 1
            continue
        
        # Use AI to evaluate
        if auto_mode:
            # In auto mode, let AI decide and apply changes
            result = ai_handler.evaluate_terminology(
                source_text, 
                target_text, 
                term_info.get('source_term', ''), 
                term_info.get('target_suggestions', []),
                model=model
            )
            
            if result['needs_fix']:
                # Apply the fix
                if update_target_text(unit, result['new_text']):
                    logging.info(f"Applied AI fix: {result['new_text']}")
                    stats['fixed'] += 1
                else:
                    logging.error("Failed to update target text")
            else:
                # Mark as ignored
                logging.info(f"AI decided no fix needed: {result['explanation']}")
                if mark_as_ignored(warning):
                    stats['ignored'] += 1
        else:
            # In interactive mode, involve the user
            process_interactive(unit, warning, term_info, source_text, target_text, model, stats)
    
    return stats

def find_terminology_errors(mqxliff_dom, debug=False):
    """Find all terminology errors in the MQXLIFF file using multiple detection methods"""
    errors = []
    
    # Method 1: Standard MemoQ error format with code 03091
    errors.extend(find_standard_errors(mqxliff_dom, debug))
    
    # Method 2: Look for terminology-related text in warnings
    errors.extend(find_terminology_text_errors(mqxliff_dom, debug))
    
    # Method 3: Look for termbase elements
    errors.extend(find_termbase_related_errors(mqxliff_dom, debug))
    
    # Log results
    if debug:
        logging.debug(f"Total terminology errors found across all methods: {len(errors)}")
    
    return errors

def find_standard_errors(mqxliff_dom, debug=False):
    """Find terminology errors with standard code 03091"""
    errors = []
    code_patterns = ['03091', 'terminology', 'term'] # Multiple possible codes/identifiers
    
    trans_units = mqxliff_dom.getElementsByTagName('trans-unit')
    if debug:
        logging.debug(f"Found {len(trans_units)} trans-unit elements")
    
    for unit in trans_units:
        # Direct warnings in the unit
        warnings_found = process_warnings_in_element(unit, code_patterns, errors)
        
        # Warnings in containers
        unit_id = unit.getAttribute('id')
        container_patterns = [
            f'mq:warnings{unit_id}', 'mq:warnings40', 'mq:warnings', 
            'warnings', 'mq:warningcontainer', 'warningcontainer'
        ]
        
        for pattern in container_patterns:
            containers = unit.getElementsByTagName(pattern)
            for container in containers:
                warnings_found += process_warnings_in_element(container, code_patterns, errors, unit)
        
        if debug and warnings_found:
            logging.debug(f"Found {warnings_found} standard warnings in unit {unit_id}")
    
    if debug:
        logging.debug(f"Found {len(errors)} standard terminology errors")
    return errors

def process_warnings_in_element(element, code_patterns, errors_list, parent_unit=None):
    """Process warnings in an element, looking for terminology errors"""
    warnings_found = 0
    unit = parent_unit if parent_unit else element
    
    # Look for different types of warning elements
    warning_patterns = ['mq:errorwarning', 'errorwarning', 'warning', 'mq:error', 'error']
    
    for pattern in warning_patterns:
        warnings = element.getElementsByTagName(pattern)
        for warning in warnings:
            # Look for error code in attributes
            found_code = False
            for attr in warning.attributes.values():
                attr_value = attr.value.lower() if attr.value else ""
                
                # Check if any pattern matches in attribute name or value
                if any(pat.lower() in attr.name.lower() for pat in code_patterns) or \
                   any(pat.lower() in attr_value for pat in code_patterns):
                    # Skip if already ignored
                    if is_warning_ignored(warning):
                        continue
                    
                    # Try to extract term info from attributes
                    term_info = extract_term_info_from_attributes(warning)
                    errors_list.append((unit, warning, term_info))
                    warnings_found += 1
                    found_code = True
                    break
            
            # If no code found in attributes, check text content
            if not found_code:
                warning_text = get_warning_text(warning).lower()
                if any(pat.lower() in warning_text for pat in code_patterns):
                    # Skip if already ignored
                    if is_warning_ignored(warning):
                        continue
                    
                    # Try to extract term info from warning text
                    term_info = extract_term_info_from_text(warning_text)
                    errors_list.append((unit, warning, term_info))
                    warnings_found += 1
    
    return warnings_found

def find_terminology_text_errors(mqxliff_dom, debug=False):
    """Find terminology errors by looking for specific texts"""
    errors = []
    term_patterns = ['term', 'terminology', 'glossary', 'termbase']
    
    trans_units = mqxliff_dom.getElementsByTagName('trans-unit')
    for unit in trans_units:
        # Look for comments or notes containing term-related words
        elements_to_check = []
        
        # Collect notes and comments
        for tag in ['note', 'comment', 'mq:comment', 'mq:note']:
            elements_to_check.extend(unit.getElementsByTagName(tag))
        
        # Check each element
        for element in elements_to_check:
            element_text = get_warning_text(element).lower()
            if any(pat in element_text for pat in term_patterns):
                # Create a pseudo-warning
                errors.append((unit, element, extract_term_info_from_text(element_text)))
    
    if debug:
        logging.debug(f"Found {len(errors)} terminology errors from text patterns")
    return errors

def find_termbase_related_errors(mqxliff_dom, debug=False):
    """Find terminology errors by looking for termbase-related elements"""
    errors = []
    
    # Look for termbase-related elements
    term_elements = []
    for tag in ['mq:termbase', 'termbase', 'mq:term', 'term']:
        term_elements.extend(mqxliff_dom.getElementsByTagName(tag))
    
    if debug:
        logging.debug(f"Found {len(term_elements)} termbase-related elements")
    
    # Process each term element
    for term_element in term_elements:
        # Find the parent trans-unit
        parent = term_element.parentNode
        unit = None
        while parent and parent.nodeType == parent.ELEMENT_NODE:
            if parent.tagName == 'trans-unit':
                unit = parent
                break
            parent = parent.parentNode
        
        if unit:
            # Create a term info dictionary
            term_info = {'source_term': '', 'target_suggestions': []}
            
            # Try to extract term data
            for attr in term_element.attributes.values():
                if 'source' in attr.name.lower():
                    term_info['source_term'] = attr.value
                elif 'target' in attr.name.lower():
                    if attr.value:
                        term_info['target_suggestions'] = [attr.value]
            
            # If we found meaningful term info, add it
            if term_info['source_term'] or term_info['target_suggestions']:
                errors.append((unit, term_element, term_info))
    
    if debug:
        logging.debug(f"Found {len(errors)} terminology errors from termbase elements")
    return errors

def get_warning_text(warning):
    """Extract text from a warning element"""
    # First try to get text directly
    text = ""
    for child in warning.childNodes:
        if child.nodeType == child.TEXT_NODE:
            text += child.data
    
    # If no text found, look for text in child elements
    if not text.strip():
        for child in warning.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                for grandchild in child.childNodes:
                    if grandchild.nodeType == grandchild.TEXT_NODE:
                        text += grandchild.data
    
    return text.strip()

def extract_term_info_from_attributes(warning):
    """Extract term information from warning attributes"""
    term_info = {'source_term': '', 'target_suggestions': []}
    
    # First try to extract from localization args, which has the most structured format
    for attr in warning.attributes.values():
        if 'localizationargs' in attr.name.lower():
            if attr.value and '\t' in attr.value:
                parts = attr.value.split('\t')
                if len(parts) >= 2:
                    term_info['source_term'] = parts[0].strip()
                    suggestions = [s.strip() for s in parts[1].split(',')]
                    term_info['target_suggestions'] = [s for s in suggestions if s]
                    return term_info
    
    # If localization args don't work, try to extract from short text or long desc
    for attr in warning.attributes.values():
        attr_name = attr.name.lower()
        attr_value = attr.value
        
        # Look for short text or long desc attributes that might contain the terms
        if 'shorttext' in attr_name or 'longdesc' in attr_name:
            # Extract source term using regex patterns
            source_pattern = r'source term\s+["\']([^"\']+)["\']'
            source_matches = re.findall(source_pattern, attr_value, re.IGNORECASE)
            if source_matches:
                term_info['source_term'] = source_matches[0]
            
            # Extract target suggestions
            target_pattern = r'[pP]ossible terms:\s+([^"\.]+)'
            target_matches = re.findall(target_pattern, attr_value, re.IGNORECASE)
            if target_matches:
                suggestions = [s.strip() for s in target_matches[0].split(',')]
                term_info['target_suggestions'] = [s for s in suggestions if s]
                
            # If we found something, return immediately
            if term_info['source_term'] or term_info['target_suggestions']:
                return term_info
    
    # If still not found, try other attribute patterns
    for attr in warning.attributes.values():
        attr_name = attr.name.lower()
        
        # Source term patterns
        if any(pat in attr_name for pat in ['source', 'src']) and any(pat in attr_name for pat in ['term', 'word']):
            term_info['source_term'] = attr.value
        
        # Target term patterns
        elif any(pat in attr_name for pat in ['target', 'tgt', 'suggest']) and any(pat in attr_name for pat in ['term', 'word']):
            if attr.value:
                suggestions = [s.strip() for s in attr.value.split(';')]
                term_info['target_suggestions'].extend([s for s in suggestions if s])
    
    return term_info

def extract_term_info_from_text(warning_text):
    """Extract term information from warning text"""
    term_info = {'source_term': '', 'target_suggestions': []}
    
    # Common patterns:
    # 1. "Term 'X' should be translated as 'Y'"
    term_pattern1 = re.compile(r"[tT]erm\s+['\"]([^'\"]+)['\"].*?['\"]([^'\"]+)['\"]")
    match = term_pattern1.search(warning_text)
    if match:
        term_info['source_term'] = match.group(1)
        term_info['target_suggestions'] = [match.group(2)]
        return term_info
    
    # 2. "Source: X, Target: Y"
    term_pattern2 = re.compile(r"[sS]ource:?\s+([^,;:]+).*?[tT]arget:?\s+([^,;:]+)")
    match = term_pattern2.search(warning_text)
    if match:
        term_info['source_term'] = match.group(1).strip()
        term_info['target_suggestions'] = [match.group(2).strip()]
        return term_info
    
    # 3. "X should be Y"
    term_pattern3 = re.compile(r"[\"\']([^\"\']+)[\"\'].*?should be.*?[\"\']([^\"\']+)[\"\']")
    match = term_pattern3.search(warning_text)
    if match:
        term_info['source_term'] = match.group(1)
        term_info['target_suggestions'] = [match.group(2)]
        return term_info
    
    # If no structured pattern found, look for any quoted texts
    quotes = re.findall(r"[\"\']([^\"\']+)[\"\']", warning_text)
    if len(quotes) >= 2:
        term_info['source_term'] = quotes[0]
        term_info['target_suggestions'] = [quotes[1]]
    elif len(quotes) == 1:
        # If only one quote, it's likely the source term
        term_info['source_term'] = quotes[0]
    
    return term_info

def extract_term_info(warning):
    """Extract term information from a warning node"""
    term_info = {'source_term': '', 'target_suggestions': []}
    
    # First try to extract from attributes using the enhanced function
    attr_term_info = extract_term_info_from_attributes(warning)
    if attr_term_info.get('source_term') or attr_term_info.get('target_suggestions'):
        return attr_term_info
    
    # If we couldn't find in attributes, try to parse from warning text
    warning_text = get_warning_text(warning)
    
    # Try regex patterns for various formats
    # Pattern 1: "Translation of source term "X" missing from the target. Possible terms: Y, Z"
    pattern1 = re.compile(r'source term\s+["\']([^"\']+)["\'].*?[pP]ossible terms:\s*([^\.]+)', re.DOTALL)
    match = pattern1.search(warning_text)
    if match:
        term_info['source_term'] = match.group(1).strip()
        suggestions = [s.strip() for s in match.group(2).split(',')]
        term_info['target_suggestions'] = [s for s in suggestions if s]
        return term_info
    
    # Pattern 2: "Term 'X' should be translated as 'Y'"
    pattern2 = re.compile(r"[tT]erm\s+['\"]([^'\"]+)['\"].*?['\"]([^'\"]+)['\"]")
    match = pattern2.search(warning_text)
    if match:
        term_info['source_term'] = match.group(1)
        term_info['target_suggestions'] = [match.group(2)]
        return term_info
    
    # Pattern 3: Simple tab or colon separated format "X: Y" or "X\tY"
    if "\t" in warning_text:
        parts = warning_text.split("\t")
        if len(parts) >= 2:
            term_info['source_term'] = parts[0].strip()
            suggestions = [s.strip() for s in parts[1].split(',')]
            term_info['target_suggestions'] = [s for s in suggestions if s]
            return term_info
    elif ":" in warning_text:
        parts = warning_text.split(":")
        if len(parts) >= 2:
            term_info['source_term'] = parts[0].strip()
            suggestions = [s.strip() for s in parts[1].split(',')]
            term_info['target_suggestions'] = [s for s in suggestions if s]
            return term_info
    
    # If no structured pattern found, look for any quoted texts
    quotes = re.findall(r"[\"\']([^\"\']+)[\"\']", warning_text)
    if len(quotes) >= 2:
        term_info['source_term'] = quotes[0]
        term_info['target_suggestions'] = [quotes[1]]
    elif len(quotes) == 1:
        # If only one quote, it's likely the source term
        term_info['source_term'] = quotes[0]
    
    # Ensure we have at least an empty list for suggestions
    if not term_info['target_suggestions']:
        term_info['target_suggestions'] = []
    
    return term_info

def is_warning_ignored(warning):
    """Check if a warning is already marked as ignored"""
    for attr in warning.attributes.values():
        if any(pat in attr.name.lower() for pat in ['ignore', 'skip', 'handled']):
            return True
    return False

def extract_source_target(unit):
    """Extract source and target text from a unit"""
    source_text = ""
    target_text = ""
    
    # Get source element
    source_elements = unit.getElementsByTagName('source')
    if source_elements:
        source_text = extract_text_content(source_elements[0])
    
    # Get target element
    target_elements = unit.getElementsByTagName('target')
    if target_elements:
        target_text = extract_text_content(target_elements[0])
    
    return source_text, target_text

def extract_text_content(node):
    """Extract text content from an XML node recursively"""
    if not node:
        return ""
    
    # Extract direct text
    result = ""
    for child in node.childNodes:
        if child.nodeType == child.TEXT_NODE:
            result += child.data
        elif child.nodeType == child.ELEMENT_NODE:
            # Skip certain elements that might contain metadata
            if child.tagName not in ['mq:meta', 'meta']:
                result += extract_text_content(child)
    
    return result.strip()

def mark_as_ignored(warning):
    """Mark a warning as ignored"""
    try:
        warning.setAttribute('mq:errorwarning-ignored', 'errorwarning-ignored')
        warning.setAttribute('mq:ignore-user', 'automated')
        warning.setAttribute('mq:ignore-note', 'Marked as ignored by QA resolver')
        return True
    except Exception as e:
        logging.error(f"Error marking warning as ignored: {str(e)}")
        return False

def update_target_text(unit, new_text):
    """Update the target text in a unit"""
    try:
        target_elements = unit.getElementsByTagName('target')
        if not target_elements:
            logging.error("No target element found in unit")
            return False
        
        target = target_elements[0]
        
        # Clear existing content
        while target.firstChild:
            target.removeChild(target.firstChild)
        
        # Add new text
        text_node = unit.ownerDocument.createTextNode(new_text)
        target.appendChild(text_node)
        
        return True
    except Exception as e:
        logging.error(f"Error updating target text: {str(e)}")
        return False

def is_term_present(suggestions, text):
    """Check if any of the suggested terms are present in the text"""
    if not suggestions or not text:
        return False
    
    text = text.lower()
    for term in suggestions:
        if term and term.lower() in text:
            return True
    
    return False

def process_interactive(unit, warning, term_info, source_text, target_text, model, stats):
    """Process an error in interactive mode with colorized output"""
    unit_id = unit.getAttribute('id')
    
    # ANSI color codes
    CYAN = '\033[36m'
    YELLOW = '\033[33m'
    GREEN = '\033[32m'
    RED = '\033[31m'
    MAGENTA = '\033[35m'
    BLUE = '\033[34m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    print("\n" + "=" * 80)
    print(f"{BOLD}{BLUE}TERMINOLOGY ERROR in unit {unit_id}{RESET}")
    print("-" * 80)
    print(f"{BOLD}SOURCE:{RESET} {CYAN}{source_text}{RESET}")
    print(f"{BOLD}TARGET:{RESET} {YELLOW}{target_text}{RESET}")
    print(f"{BOLD}SOURCE TERM:{RESET} {GREEN}{term_info.get('source_term', 'unknown')}{RESET}")
    print(f"{BOLD}TARGET SUGGESTIONS:{RESET} {MAGENTA}{', '.join(term_info.get('target_suggestions', []))}{RESET}")
    print("-" * 80)
    
    # Get AI suggestion
    result = ai_handler.evaluate_terminology(
        source_text, 
        target_text, 
        term_info.get('source_term', ''), 
        term_info.get('target_suggestions', []),
        model=model
    )
    
    print(f"{BOLD}AI ANALYSIS:{RESET} {RED}{result['explanation']}{RESET}")
    
    if result['needs_fix']:
        print(f"{BOLD}SUGGESTED FIX:{RESET} {GREEN}{result['new_text']}{RESET}")
    
    print("-" * 80)
    
    # Ask user for action
    choice = input(f"{BOLD}Actions:{RESET} ({GREEN}f{RESET})ix with AI suggestion, ({YELLOW}e{RESET})dit manually, ({BLUE}i{RESET})gnore, ({RED}s{RESET})kip: ").lower()
    
    if choice == 'f' and result['needs_fix']:
        # Apply AI fix
        if update_target_text(unit, result['new_text']):
            print(f"{GREEN}Applied AI fix{RESET}")
            stats['fixed'] += 1
        else:
            print(f"{RED}Failed to apply fix{RESET}")
    elif choice == 'e':
        # Manual edit
        new_text = input(f"{YELLOW}Enter new text:{RESET} ")
        if update_target_text(unit, new_text):
            print(f"{GREEN}Applied manual fix{RESET}")
            stats['fixed'] += 1
        else:
            print(f"{RED}Failed to apply fix{RESET}")
    elif choice == 'i':
        # Ignore
        if mark_as_ignored(warning):
            print(f"{BLUE}Marked as ignored{RESET}")
            stats['ignored'] += 1
        else:
            print(f"{RED}Failed to mark as ignored{RESET}")
    else:
        # Skip
        print(f"{RED}Skipped{RESET}")
    
    print("=" * 80)