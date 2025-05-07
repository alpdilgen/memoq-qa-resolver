"""Report generation for QA resolver"""
import os
import datetime
import logging

def generate_report(file_path, stats):
    """Generate a report of the QA resolution process
    
    Args:
        file_path: Path to the processed file
        stats: Statistics dictionary with 'fixed' and 'ignored' counts
        
    Returns:
        str: Path to the generated report
    """
    try:
        # Create report filename
        base_name = os.path.basename(file_path)
        report_file = f"report_{base_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        # Write report
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"QA ERROR RESOLUTION REPORT\n")
            f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"File: {file_path}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Errors fixed: {stats['fixed']}\n")
            f.write(f"Errors ignored: {stats['ignored']}\n")
            f.write(f"Total processed: {stats['fixed'] + stats['ignored']}\n\n")
            
            f.write("=" * 80 + "\n")
            f.write("End of report\n")
        
        logging.info(f"Report generated: {report_file}")
        return report_file
    
    except Exception as e:
        logging.error(f"Error generating report: {str(e)}")
        return None