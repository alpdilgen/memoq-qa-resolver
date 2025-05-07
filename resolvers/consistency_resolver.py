"""MemoQ Consistency Error Resolver Module"""
import logging
import re
from common import utils, ai_handler

def process(mqxliff_dom, auto_mode=False, model="gpt-4", debug=False):
    """Process consistency errors (codes 03100, 03101) in the MQXLIFF file
    
    Args:
        mqxliff_dom: The parsed MQXLIFF DOM
        auto_mode: Whether to run in automatic mode
        model: The OpenAI model to use
        debug: Whether to enable debug logging
        
    Returns:
        dict: Statistics about the processing
    """
    stats = {'fixed': 0, 'ignored': 0, 'total': 0}
    
    # Find all consistency errors
    consistency_errors = find_consistency_errors(mqxliff_dom, debug)
    stats['total'] = len(consistency_errors)
    
    logging.info(f"Found {stats['total']} consistency errors")
    
    # Process each error if any found
    if stats['total'] > 0:
        if auto_mode:
            # Automatic mode
            for i, (unit, warning, consistency_info) in enumerate(consistency_errors):
                logging.info(f"Processing consistency error {i+1}/{stats['total']} automatically")
                process_automatic(unit, warning, consistency_info, model, stats)
        else:
            # Interactive mode
            for i, (unit, warning, consistency_info) in enumerate(consistency_errors):
                logging.info(f"Processing consistency error {i+1}/{stats['total']} interactively")
                process_interactive(unit, warning, consistency_info, model, stats)
    
    return stats

def find_consistency_errors(mqxliff_dom, debug=False):
    """Find all consistency errors in the MQXLIFF file"""
    errors = []
    code_patterns = ['03100', '03101', 'consistency', 'inconsist']  # Multiple possible codes/identifiers
    
    trans_units = mqxliff_dom.getElementsByTagName('trans-unit')
    if debug:
        logging.debug(f"Found {len(trans_units)} trans-unit elements")
    
    for unit in trans_units:
        # Direct warnings in the unit
        warnings_found = process_consistency_warnings(unit, code_patterns, errors)
        
        # Warnings in containers
        unit_id = unit.getAttribute('id')
        container_patterns = [
            f'mq:warnings{unit_id}', 'mq:warnings40', 'mq:warnings', 
            'warnings', 'mq:warningcontainer', 'warningcontainer'
        ]
        
        for pattern in container_patterns:
            containers = unit.getElementsByTagName(pattern)
            for container in containers:
                warnings_found += process_consistency_warnings(container, code_patterns, errors, unit)
        
        if debug and warnings_found:
            logging.debug(f"Found {warnings_found} consistency warnings in unit {unit_id}")
    
    if debug:
        logging.debug(f"Found {len(errors)} consistency errors total")
    
    return errors

def process_consistency_warnings(element, code_patterns, errors_list, parent_unit=None):
    """Process warnings in an element, looking for consistency errors"""
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
                    
                    # Try to extract consistency info from attributes
                    consistency_info = extract_consistency_info(warning, unit)
                    errors_list.append((unit, warning, consistency_info))
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
                    
                    # Extract consistency info from warning text
                    consistency_info = extract_consistency_info_from_text(warning_text, unit)
                    errors_list.append((unit, warning, consistency_info))
                    warnings_found += 1
    
    return warnings_found

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

def is_warning_ignored(warning):
    """Check if a warning is already marked as ignored"""
    for attr in warning.attributes.values():
        if any(pat in attr.name.lower() for pat in ['ignore', 'skip', 'handled']):
            return True
    return False

def extract_consistency_info(warning, unit):
    """Extract consistency information from warning attributes"""
    consistency_info = {
        'inconsistent_text': '',
        'consistent_text': '',
        'context': '',
        'related_segments': []
    }
    
    # First try to get from localization args
    for attr in warning.attributes.values():
        if 'localizationargs' in attr.name.lower():
            if attr.value and '\t' in attr.value:
                parts = attr.value.split('\t')
                if len(parts) >= 2:
                    consistency_info['consistent_text'] = parts[0].strip()  # First part is usually the "correct" term
                    consistency_info['inconsistent_text'] = parts[1].strip()  # Second part is the term being used
                    return consistency_info
    
    # Try to extract info from shorttext and longdesc
    shorttext = ""
    longdesc = ""
    
    for attr in warning.attributes.values():
        attr_name = attr.name.lower()
        
        if 'shorttext' in attr_name:
            shorttext = attr.value
        elif 'longdesc' in attr_name:
            longdesc = attr.value
    
    # Extract from shorttext (e.g., "Inconsistent translation for Diagnostics")
    if "inconsistent translation for" in shorttext.lower():
        parts = shorttext.split("for", 1)
        if len(parts) > 1:
            consistency_info['inconsistent_text'] = parts[1].strip()
    
    # Extract from longdesc (e.g., "The same segment was also translated as: TEŞHİS")
    if "translated as:" in longdesc.lower():
        parts = longdesc.split("as:", 1)
        if len(parts) > 1:
            consistency_info['consistent_text'] = parts[1].strip()
    
    # If we have partial information, try other attributes or text patterns
    if not consistency_info['consistent_text'] or not consistency_info['inconsistent_text']:
        for attr in warning.attributes.values():
            attr_name = attr.name.lower()
            
            if 'inconsist' in attr_name or 'current' in attr_name:
                consistency_info['inconsistent_text'] = attr.value
            elif 'consist' in attr_name or 'expected' in attr_name or 'previous' in attr_name:
                consistency_info['consistent_text'] = attr.value
            elif 'segment' in attr_name or 'related' in attr_name:
                if attr.value:
                    segments = [s.strip() for s in attr.value.split(';')]
                    consistency_info['related_segments'].extend([s for s in segments if s])
    
    # If we still don't have both texts, try to parse from warning text
    if not consistency_info['consistent_text'] or not consistency_info['inconsistent_text']:
        warning_text = get_warning_text(warning)
        text_info = extract_consistency_info_from_text(warning_text, unit)
        
        # Only update missing fields
        if not consistency_info['consistent_text']:
            consistency_info['consistent_text'] = text_info['consistent_text']
        if not consistency_info['inconsistent_text']:
            consistency_info['inconsistent_text'] = text_info['inconsistent_text']
        if not consistency_info['related_segments'] and text_info['related_segments']:
            consistency_info['related_segments'] = text_info['related_segments']
    
    # Also get source/target text for context
    source_text, target_text = extract_source_target(unit)
    consistency_info['context'] = f"Source: {source_text}\nTarget: {target_text}"
    
    return consistency_info

def extract_consistency_info_from_text(warning_text, unit):
    """Extract consistency information from warning text"""
    info = {
        'inconsistent_text': '',
        'consistent_text': '',
        'related_segments': []
    }
    
    # Common patterns in consistency warnings:
    # 1. "Inconsistent translation for X"
    pattern1 = re.compile(r"[iI]nconsistent\s+translation\s+for\s+([^\.]+)")
    match = pattern1.search(warning_text)
    if match:
        info['inconsistent_text'] = match.group(1).strip()
    
    # 2. "The same segment was also translated as: Y"
    pattern2 = re.compile(r"translated\s+as:\s+([^\.]+)")
    match = pattern2.search(warning_text)
    if match:
        info['consistent_text'] = match.group(1).strip()
    
    # 3. "X should be Y"
    pattern3 = re.compile(r"['\"]([^'\"]+)['\"].*?should be.*?['\"]([^'\"]+)['\"]")
    match = pattern3.search(warning_text)
    if match:
        info['inconsistent_text'] = match.group(1)
        info['consistent_text'] = match.group(2)
    
    # 4. "Inconsistent with [segment X]: 'A' vs 'B'"
    pattern4 = re.compile(r"[iI]nconsistent with.*?segment[s]?\s+([0-9,\s]+).*?['\"]([^'\"]+)['\"].*?['\"]([^'\"]+)['\"]")
    match = pattern4.search(warning_text)
    if match:
        info['related_segments'] = [s.strip() for s in match.group(1).split(',')]
        # Figure out which is inconsistent (current) and which is consistent (previous)
        info['inconsistent_text'] = match.group(3)  # Assuming the latter is current
        info['consistent_text'] = match.group(2)    # Assuming the former is previous
    
    # 5. Try tab-separated format "X\tY"
    if "\t" in warning_text:
        parts = warning_text.split("\t")
        if len(parts) >= 2:
            info['consistent_text'] = parts[0].strip()  # First part is typically the correct/previous term
            info['inconsistent_text'] = parts[1].strip()  # Second part is typically the current term
    
    # 6. Look for segment references
    segments = re.findall(r"segment[s]?\s+([0-9]+)", warning_text)
    if segments:
        info['related_segments'] = segments
    
    return info

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

def process_automatic(unit, warning, consistency_info, model, stats):
    """Process a consistency error in automatic mode"""
    unit_id = unit.getAttribute('id')
    source_text, target_text = extract_source_target(unit)
    
    logging.info(f"Processing consistency error in unit {unit_id} automatically")
    
    # Use AI to evaluate
    result = ai_handler.analyze_consistency(
        source_text,
        target_text,
        consistency_info.get('consistent_text', ''),
        consistency_info.get('inconsistent_text', ''),
        consistency_info.get('related_segments', []),
        model=model
    )
    
    if result.get('needs_fix', False):
        # Apply the fix
        if update_target_text(unit, result.get('new_text', '')):
            logging.info(f"Applied AI fix for consistency error")
            stats['fixed'] += 1
        else:
            logging.error("Failed to update target text")
    else:
        # Mark as ignored
        logging.info(f"AI decided no consistency fix needed")
        if mark_as_ignored(warning):
            stats['ignored'] += 1
        else:
            logging.error("Failed to mark warning as ignored")

def process_interactive(unit, warning, consistency_info, model, stats):
    """Process a consistency error in interactive mode with colorized output"""
    unit_id = unit.getAttribute('id')
    source_text, target_text = extract_source_target(unit)
    
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
    print(f"{BOLD}{BLUE}CONSISTENCY ERROR in unit {unit_id}{RESET}")
    print("-" * 80)
    print(f"{BOLD}SOURCE:{RESET} {CYAN}{source_text}{RESET}")
    print(f"{BOLD}TARGET:{RESET} {YELLOW}{target_text}{RESET}")
    print(f"{BOLD}CONSISTENT TEXT:{RESET} {GREEN}{consistency_info.get('consistent_text', 'unknown')}{RESET}")
    print(f"{BOLD}INCONSISTENT TEXT:{RESET} {RED}{consistency_info.get('inconsistent_text', 'unknown')}{RESET}")
    
    if consistency_info.get('related_segments'):
        print(f"{BOLD}RELATED SEGMENTS:{RESET} {MAGENTA}{', '.join(consistency_info.get('related_segments', []))}{RESET}")
    
    print("-" * 80)
    
    # Use AI to evaluate
    result = ai_handler.analyze_consistency(
        source_text,
        target_text,
        consistency_info.get('consistent_text', ''),
        consistency_info.get('inconsistent_text', ''),
        consistency_info.get('related_segments', []),
        model=model
    )
    
    print(f"{BOLD}AI ANALYSIS:{RESET} {CYAN}{result.get('explanation', 'No AI analysis available')}{RESET}")
    
    if result.get('needs_fix', False):
        print(f"{BOLD}SUGGESTED FIX:{RESET} {GREEN}{result.get('new_text', '')}{RESET}")
    
    print("-" * 80)
    
    # Ask user for action
    choice = input(f"{BOLD}Actions:{RESET} ({GREEN}f{RESET})ix with AI suggestion, ({YELLOW}e{RESET})dit manually, ({BLUE}i{RESET})gnore, ({RED}s{RESET})kip: ").lower()
    
    if choice == 'f' and result.get('needs_fix', False):
        # Apply AI fix
        if update_target_text(unit, result.get('new_text', '')):
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