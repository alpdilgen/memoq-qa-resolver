"""MemoQ MQXLIFF File Handling Utilities"""
import os
import re
import datetime
import logging
from xml.dom import minidom

def parse_file(file_path):
    """Parse an MQXLIFF file and return the DOM
    
    Args:
        file_path: Path to the MQXLIFF file
        
    Returns:
        minidom.Document: The parsed DOM
    """
    try:
        # Create backup
        create_backup(file_path)
        
        # Parse the file
        logging.info(f"Parsing {file_path}...")
        dom = minidom.parse(file_path)
        logging.info(f"Successfully parsed {file_path}")
        return dom
    except Exception as e:
        logging.error(f"Error parsing file: {str(e)}")
        return None

def create_backup(file_path):
    """Create a backup of the file"""
    try:
        backup_file = f"{file_path}.backup-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        with open(file_path, 'rb') as src, open(backup_file, 'wb') as dst:
            dst.write(src.read())
        logging.info(f"Created backup at {backup_file}")
        return backup_file
    except Exception as e:
        logging.error(f"Error creating backup: {str(e)}")
        return None

def save_file(dom, file_path):
    """Save the DOM back to the file"""
    try:
        logging.info(f"Saving changes to {file_path}")
        
        # Get XML content
        xml_content = dom.toxml(encoding='utf-8').decode('utf-8')
        
        # Fix XML declaration if needed
        if xml_content.count('<?xml') > 1:
            xml_content = xml_content[xml_content.find('<?xml'):]
            xml_content = re.sub(r'(<\?xml[^>]*>).*?(<\?xml[^>]*>)', r'\1', xml_content)
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
            
        logging.info(f"Changes saved successfully")
        return True
    except Exception as e:
        logging.error(f"Error saving file: {str(e)}")
        return False

def ignore_remaining_errors(dom, processed_categories=None):
    """Mark all errors not in processed categories as ignored"""
    if processed_categories is None:
        processed_categories = []
    
    flat_codes = []
    for codes in processed_categories:
        if isinstance(codes, list):
            flat_codes.extend(codes)
        else:
            flat_codes.append(codes)
    
    # Find all warning nodes
    ignored_count = 0
    trans_units = dom.getElementsByTagName('trans-unit')
    
    for unit in trans_units:
        # Process warnings
        for tag_name in ['mq:errorwarning', 'errorwarning']:
            warnings = []
            
            # Direct warnings
            direct_warnings = unit.getElementsByTagName(tag_name)
            warnings.extend(direct_warnings)
            
            # Warnings in containers
            unit_id = unit.getAttribute('id')
            for container_name in [f'mq:warnings{unit_id}', 'mq:warnings40', 'mq:warnings']:
                containers = unit.getElementsByTagName(container_name)
                for container in containers:
                    container_warnings = container.getElementsByTagName(tag_name)
                    warnings.extend(container_warnings)
            
            # Process each warning
            for warning in warnings:
                # Check if already ignored
                already_ignored = False
                for attr in warning.attributes.values():
                    if 'errorwarning-ignored' in attr.name.lower():
                        already_ignored = True
                        break
                
                if already_ignored:
                    continue
                
                # Get error code
                error_code = None
                for attr in warning.attributes.values():
                    if ('code' in attr.name.lower() or 'errorwarning-code' in attr.name.lower()):
                        error_code = attr.value
                        break
                
                # Skip if in processed categories
                if error_code in flat_codes:
                    continue
                
                # Mark as ignored
                warning.setAttribute('mq:errorwarning-ignored', 'errorwarning-ignored')
                warning.setAttribute('mq:ignore-user', 'ada')
                warning.setAttribute('mq:ignore-note', '')
                ignored_count += 1
    
    return ignored_count