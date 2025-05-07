#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import datetime
import importlib
from common import file_handler, report_handler, utils

# Define error categories and their codes
ERROR_CATEGORIES = {
    'consistency': {'codes': ['03100', '03101'], 'module': 'resolvers.consistency_resolver'},
    'terminology': {'codes': ['03091'], 'module': 'resolvers.terminology_resolver'},
    # Add other categories here
}

def parse_arguments():
    parser = argparse.ArgumentParser(description='MemoQ QA Error Resolution Tool')
    parser.add_argument('--file', '-f', required=True, help='Target MQXLIFF file to process')
    parser.add_argument('--categories', '-c', default='all',
                       help='Comma-separated list of error categories to process (default: all)')
    parser.add_argument('--auto', '-a', action='store_true', help='Run in fully automatic mode')
    parser.add_argument('--model', '-m', default='gpt-4', help='OpenAI model to use (default: gpt-4)')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug logging')
    parser.add_argument('--ignore-remaining', '-i', action='store_true',
                       help='Mark all non-processed errors as ignored')
    return parser.parse_args()

def setup_logging(debug=False):
    log_file = f"qa_resolver_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return log_file

def get_categories_to_process(categories_arg):
    if categories_arg.lower() == 'all':
        return list(ERROR_CATEGORIES.keys())
    
    requested_categories = [c.strip().lower() for c in categories_arg.split(',')]
    valid_categories = [c for c in requested_categories if c in ERROR_CATEGORIES]
    
    if len(valid_categories) != len(requested_categories):
        invalid_cats = set(requested_categories) - set(valid_categories)
        logging.warning(f"Ignoring invalid categories: {', '.join(invalid_cats)}")
    
    return valid_categories

def count_errors(mqxliff_dom, category):
    """Count errors in a specific category"""
    try:
        # Import the module for this category
        module_name = ERROR_CATEGORIES[category]['module']
        module = importlib.import_module(module_name)
        
        # Use the find_errors function
        if category == 'terminology':
            errors = module.find_terminology_errors(mqxliff_dom)
            return len(errors)
        elif category == 'consistency':
            errors = module.find_consistency_errors(mqxliff_dom)
            return len(errors)
        else:
            return 0
    except Exception as e:
        logging.error(f"Error counting {category} errors: {str(e)}")
        return 0

def process_category_with_updates(category, mqxliff_dom, args, progress_callback=None):
    """Process a single error category with progress updates"""
    try:
        # Import the module for this category
        module_name = ERROR_CATEGORIES[category]['module']
        module = importlib.import_module(module_name)
        
        # Get the errors first
        if category == 'terminology':
            errors = module.find_terminology_errors(mqxliff_dom, args.debug)
        elif category == 'consistency':
            errors = module.find_consistency_errors(mqxliff_dom, args.debug)
        else:
            errors = []
            
        total_errors = len(errors)
        logging.info(f"Found {total_errors} {category} errors")
        result = {'fixed': 0, 'ignored': 0, 'total': total_errors}
        
        # Process each error
        for i, (unit, warning, error_info) in enumerate(errors):
            # Extract context
            unit_id = unit.getAttribute('id')
            source_text, target_text = module.extract_source_target(unit)
            
            # Update progress if callback provided
            if progress_callback:
                if category == 'terminology':
                    term_info = error_info if error_info else module.extract_term_info(warning)
                    progress_callback(
                        unit_id, 
                        category, 
                        i+1, 
                        total_errors,
                        term_info.get('source_term', ''),
                        ", ".join(term_info.get('target_suggestions', []))
                    )
                else:
                    progress_callback(
                        unit_id,
                        category,
                        i+1,
                        total_errors,
                        error_info.get('consistent_text', ''),
                        error_info.get('inconsistent_text', '')
                    )
            
            # Process the error (this would need to be customized for each resolver)
            # This simplified stub just counts interactions
            if args.auto:
                # In auto mode
                if category == 'terminology':
                    term_info = error_info if error_info else module.extract_term_info(warning)
                    result_analysis = module.ai_handler.evaluate_terminology(
                        source_text, 
                        target_text, 
                        term_info.get('source_term', ''), 
                        term_info.get('target_suggestions', []),
                        model=args.model
                    )
                    
                    if result_analysis.get('needs_fix', False):
                        if module.update_target_text(unit, result_analysis.get('new_text', '')):
                            result['fixed'] += 1
                        else:
                            logging.error(f"Failed to update text in unit {unit_id}")
                    else:
                        if module.mark_as_ignored(warning):
                            result['ignored'] += 1
                else:
                    # Consistency handling
                    result_analysis = module.ai_handler.analyze_consistency(
                        source_text,
                        target_text,
                        error_info.get('consistent_text', ''),
                        error_info.get('inconsistent_text', ''),
                        error_info.get('related_segments', []),
                        model=args.model
                    )
                    
                    if result_analysis.get('needs_fix', False):
                        if module.update_target_text(unit, result_analysis.get('new_text', '')):
                            result['fixed'] += 1
                        else:
                            logging.error(f"Failed to update text in unit {unit_id}")
                    else:
                        if module.mark_as_ignored(warning):
                            result['ignored'] += 1
            else:
                # Call the standard process function for interactive mode
                module_result = module.process(
                    mqxliff_dom=mqxliff_dom,
                    auto_mode=args.auto,
                    model=args.model,
                    debug=args.debug
                )
                return module_result
        
        logging.info(f"Completed {category} processing: {result['fixed']} fixed, {result['ignored']} ignored")
        return result
    except Exception as e:
        logging.error(f"Error processing {category}: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return {'fixed': 0, 'ignored': 0, 'errors': 1}

def process_category(category, mqxliff_dom, args):
    """Process a single error category using its dedicated resolver"""
    try:
        # Import the module for this category
        module_name = ERROR_CATEGORIES[category]['module']
        module = importlib.import_module(module_name)
        
        # Call the process function from the module
        logging.info(f"Processing {category} errors...")
        result = module.process(
            mqxliff_dom=mqxliff_dom,
            auto_mode=args.auto,
            model=args.model,
            debug=args.debug
        )
        
        logging.info(f"Completed {category} processing: {result['fixed']} fixed, {result['ignored']} ignored")
        return result
    except Exception as e:
        logging.error(f"Error processing {category}: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return {'fixed': 0, 'ignored': 0, 'errors': 1}

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # Setup logging
    log_file = setup_logging(args.debug)
    
    try:
        # Log start and configuration
        logging.info("=" * 80)
        logging.info(f"MemoQ QA Error Resolution Tool - Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"File: {args.file}")
        logging.info(f"Mode: {'Automatic' if args.auto else 'Interactive'}")
        logging.info(f"Model: {args.model}")
        logging.info("=" * 80)
        
        # Validate file exists
        if not os.path.exists(args.file):
            logging.error(f"Error: File {args.file} not found.")
            sys.exit(1)
        
        # Get categories to process
        categories = get_categories_to_process(args.categories)
        if not categories:
            logging.error("No valid categories to process. Exiting.")
            sys.exit(1)
        
        logging.info(f"Will process the following categories: {', '.join(categories)}")
        
        # Parse the MQXLIFF file
        mqxliff_dom = file_handler.parse_file(args.file)
        if not mqxliff_dom:
            logging.error("Failed to parse the MQXLIFF file.")
            sys.exit(1)
        
        # Process each category
        total_stats = {'fixed': 0, 'ignored': 0}
        for category in categories:
            category_stats = process_category(category, mqxliff_dom, args)
            total_stats['fixed'] += category_stats['fixed']
            total_stats['ignored'] += category_stats['ignored']
            
            # Save intermediate results after each category
            if category_stats['fixed'] > 0 or category_stats['ignored'] > 0:
                file_handler.save_file(mqxliff_dom, args.file)
        
        # Ignore remaining errors if requested
        if args.ignore_remaining:
            ignored_count = file_handler.ignore_remaining_errors(
                mqxliff_dom, 
                processed_categories=[ERROR_CATEGORIES[c]['codes'] for c in categories]
            )
            logging.info(f"Ignored {ignored_count} remaining errors")
            total_stats['ignored'] += ignored_count
            
            # Save final changes
            file_handler.save_file(mqxliff_dom, args.file)
        
        # Generate final report
        report_file = report_handler.generate_report(args.file, total_stats)
        
        # Log completion
        logging.info("=" * 80)
        logging.info(f"Process completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"Results: {total_stats['fixed']} fixed, {total_stats['ignored']} ignored")
        logging.info(f"Report saved to: {report_file}")
        logging.info(f"Log file: {log_file}")
        logging.info("=" * 80)
        
        print(f"\nComplete! Fixed {total_stats['fixed']} errors and ignored {total_stats['ignored']} errors.")
        print(f"See {report_file} for details and {log_file} for full log.")
        
    except KeyboardInterrupt:
        logging.info("Process interrupted by user.")
        print("\nProcess interrupted. Partial results may have been saved.")
    except Exception as e:
        logging.critical(f"Unhandled exception: {str(e)}")
        import traceback
        logging.critical(traceback.format_exc())
        print(f"\nAn error occurred. See {log_file} for details.")
        
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
