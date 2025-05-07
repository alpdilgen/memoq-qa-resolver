import streamlit as st
import os
import tempfile
import sys
import subprocess
import logging
from io import StringIO
from pathlib import Path

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import our modules
from common import file_handler
from qa_resolver import process_category, get_categories_to_process, ERROR_CATEGORIES
import importlib

st.set_page_config(
    page_title="MemoQ QA Error Resolver",
    page_icon="🔍",
    layout="wide"
)

st.title("MemoQ QA Error Resolver")
st.markdown("Upload your MemoQ MQXLIFF file to detect and fix QA errors")

# Sidebar for settings
st.sidebar.header("Settings")
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password")
if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key

model = st.sidebar.selectbox(
    "AI Model",
    ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"],
    index=0
)

categories = st.sidebar.multiselect(
    "Error Categories",
    ["terminology", "consistency"],
    default=["terminology", "consistency"]
)

auto_mode = st.sidebar.checkbox("Automatic Mode (No User Interaction)", value=False)
debug_mode = st.sidebar.checkbox("Debug Mode", value=False)
ignore_remaining = st.sidebar.checkbox("Ignore Remaining Errors", value=False)

# File uploader
uploaded_file = st.file_uploader("Choose an MQXLIFF file", type=["mqxliff"])

if uploaded_file is not None:
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mqxliff") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name
    
    st.success(f"File uploaded successfully: {uploaded_file.name}")
    
    # Process button
    if st.button("Process File"):
        # Set up progress tracking elements
        progress_container = st.container()
        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
            current_unit_text = st.empty()
            current_error_text = st.empty()
            error_details_text = st.empty()
        
        with st.spinner("Processing your file..."):
            try:
                # Set up logging to capture output
                log_stream = StringIO()
                handler = logging.StreamHandler(log_stream)
                logger = logging.getLogger()
                logger.setLevel(logging.INFO)
                logger.addHandler(handler)
                
                # Parse MQXLIFF file
                status_text.text("Parsing MQXLIFF file...")
                mqxliff_dom = file_handler.parse_file(tmp_path)
                if not mqxliff_dom:
                    st.error("Failed to parse the MQXLIFF file.")
                else:
                    # Process each category
                    total_stats = {'fixed': 0, 'ignored': 0, 'total': 0}
                    cat_list = get_categories_to_process(",".join(categories))
                    
                    # Create args object to pass to process_category
                    class Args:
                        pass
                    args = Args()
                    args.auto = auto_mode
                    args.model = model
                    args.debug = debug_mode
                    
                    # Count total errors first
                    status_text.text("Counting errors...")
                    
                    for category in cat_list:
                        # Import the specific resolver
                        if category == 'terminology':
                            module_name = ERROR_CATEGORIES[category]['module']
                            module = importlib.import_module(module_name)
                            errors = module.find_terminology_errors(mqxliff_dom, debug_mode)
                            category_total = len(errors)
                        elif category == 'consistency':
                            module_name = ERROR_CATEGORIES[category]['module']
                            module = importlib.import_module(module_name)
                            errors = module.find_consistency_errors(mqxliff_dom, debug_mode)
                            category_total = len(errors)
                        else:
                            category_total = 0
                            
                        total_stats['total'] += category_total
                        status_text.text(f"Found {category_total} {category} errors")
                    
                    # Process each category with progress updates
                    if total_stats['total'] > 0:
                        processed_count = 0
                        error_tracking = []
                        
                        for category in cat_list:
                            status_text.text(f"Processing {category} errors...")
                            
                            # Import the specific resolver
                            module_name = ERROR_CATEGORIES[category]['module']
                            module = importlib.import_module(module_name)
                            
                            # Get the errors
                            if category == 'terminology':
                                errors = module.find_terminology_errors(mqxliff_dom, debug_mode)
                            elif category == 'consistency':
                                errors = module.find_consistency_errors(mqxliff_dom, debug_mode)
                            else:
                                errors = []
                                
                            # Process each error
                            category_stats = {'fixed': 0, 'ignored': 0}
                            for i, (unit, warning, error_info) in enumerate(errors):
                                # Extract info
                                unit_id = unit.getAttribute('id')
                                source_text, target_text = module.extract_source_target(unit)
                                
                                # Update progress display
                                current_unit_text.text(f"Processing unit: {unit_id}")
                                current_error_text.text(f"Error {i+1}/{len(errors)} ({category})")
                                
                                if category == 'terminology':
                                    term_info = error_info if error_info else module.extract_term_info(warning)
                                    error_details_text.text(f"Term: {term_info.get('source_term', '')} → Suggestions: {', '.join(term_info.get('target_suggestions', []))}")
                                else:
                                    consistency_info = error_info
                                    error_details_text.text(f"Consistent: {consistency_info.get('consistent_text', '')} → Inconsistent: {consistency_info.get('inconsistent_text', '')}")
                                
                                # Process with the regular function
                                if auto_mode:
                                    # Auto mode processing
                                    if category == 'terminology':
                                        result = module.ai_handler.evaluate_terminology(
                                            source_text, 
                                            target_text, 
                                            term_info.get('source_term', ''), 
                                            term_info.get('target_suggestions', []),
                                            model=model
                                        )
                                        
                                        if result['needs_fix']:
                                            if module.update_target_text(unit, result['new_text']):
                                                category_stats['fixed'] += 1
                                            else:
                                                st.error(f"Failed to update text in unit {unit_id}")
                                        else:
                                            if module.mark_as_ignored(warning):
                                                category_stats['ignored'] += 1
                                    else:
                                        # Consistency handling
                                        result = module.ai_handler.analyze_consistency(
                                            source_text,
                                            target_text,
                                            consistency_info.get('consistent_text', ''),
                                            consistency_info.get('inconsistent_text', ''),
                                            consistency_info.get('related_segments', []),
                                            model=model
                                        )
                                        
                                        if result.get('needs_fix', False):
                                            if module.update_target_text(unit, result.get('new_text', '')):
                                                category_stats['fixed'] += 1
                                            else:
                                                st.error(f"Failed to update text in unit {unit_id}")
                                        else:
                                            if module.mark_as_ignored(warning):
                                                category_stats['ignored'] += 1
                                else:
                                    # Interactive mode processing - done through CLI, no UI interaction here
                                    # Interactive mode can't be properly implemented in Streamlit without redesigning
                                    st.warning(f"Interactive mode is not supported in the web interface. Please use Auto mode.")
                                    break
                                
                                # Update progress bar
                                processed_count += 1
                                progress_bar.progress(processed_count / total_stats['total'] if total_stats['total'] > 0 else 1.0)
                                
                                # Add brief delay to allow UI updates
                                import time
                                time.sleep(0.1)
                            
                            # Update total stats
                            total_stats['fixed'] += category_stats['fixed']
                            total_stats['ignored'] += category_stats['ignored']
                            
                            # Save intermediate results
                            if category_stats['fixed'] > 0 or category_stats['ignored'] > 0:
                                status_text.text(f"Saving changes after processing {category} errors...")
                                file_handler.save_file(mqxliff_dom, tmp_path)
                                
                            status_text.text(f"Completed {category}: {category_stats['fixed']} fixed, {category_stats['ignored']} ignored")
                    
                    # Ignore remaining errors if requested
                    if ignore_remaining:
                        status_text.text("Ignoring remaining errors...")
                        ignored_count = file_handler.ignore_remaining_errors(
                            mqxliff_dom, 
                            processed_categories=[ERROR_CATEGORIES[c]['codes'] for c in cat_list]
                        )
                        status_text.text(f"Ignored {ignored_count} remaining errors")
                        total_stats['ignored'] += ignored_count
                        
                        # Save final changes
                        file_handler.save_file(mqxliff_dom, tmp_path)
                    
                    # Show results
                    progress_bar.progress(1.0)
                    status_text.text(f"Processing complete! Fixed {total_stats['fixed']} errors and ignored {total_stats['ignored']} errors.")
                    current_unit_text.empty()
                    current_error_text.empty()
                    error_details_text.empty()
                    
                    # Provide download link for processed file
                    with open(tmp_path, "rb") as file:
                        processed_file = file.read()
                        
                    st.download_button(
                        label="Download Processed File",
                        data=processed_file,
                        file_name=uploaded_file.name,
                        mime="application/octet-stream"
                    )
                    
                    # Show logs
                    st.text_area("Processing Logs", log_stream.getvalue(), height=300)
                        
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")
                import traceback
                st.text_area("Error Details", traceback.format_exc(), height=200)
                
                # Clear progress display on error
                progress_bar.empty()
                status_text.empty()
                current_unit_text.empty()
                current_error_text.empty()
                error_details_text.empty()
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_path)
                except:
                    pass

st.markdown("---")
st.markdown("### How to Use")
st.markdown("""
1. Enter your OpenAI API key in the sidebar
2. Upload an MQXLIFF file
3. Select error categories to process
4. Choose between automatic or interactive mode
5. Click 'Process File'
6. Download the processed file when complete
""")
