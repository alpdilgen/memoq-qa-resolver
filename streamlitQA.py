import streamlit as st
import os
import tempfile
import sys
import subprocess
import logging
import time
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
        # Create a container for progress elements
        progress_container = st.container()
        
        # Keep track of processing info in session state
        if "processing_info" not in st.session_state:
            st.session_state.processing_info = {
                "status": "Not started",
                "current_unit": "",
                "current_error": "",
                "error_details": "",
                "progress": 0,
                "total_errors": 0,
                "processed_count": 0
            }
            
        # Create progress tracking elements
        with progress_container:
            # Visual progress bar
            progress_bar = st.progress(0)
            
            # Progress metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                status_metric = st.empty()
            with col2:
                progress_metric = st.empty()
            with col3:
                time_metric = st.empty()
                
            # Status text for detailed information
            status_text = st.empty()
            current_unit_text = st.empty()
            current_error_text = st.empty()
            
            # Error details with colorful display
            error_details = st.container()
            with error_details:
                source_term_col, target_suggestions_col = st.columns(2)
                with source_term_col:
                    source_term_text = st.empty()
                with target_suggestions_col:
                    target_suggestions_text = st.empty()
        
        log_container = st.expander("Processing Logs", expanded=False)
        log_output = log_container.empty()

        start_time = time.time()
        
        # Initialize processing info
        st.session_state.processing_info["status"] = "Starting"
        st.session_state.processing_info["progress"] = 0
        status_metric.metric("Status", "Starting")
        progress_metric.metric("Progress", "0%")
        time_metric.metric("Time", "0s")
            
        with st.spinner("Processing your file..."):
            try:
                # Set up logging to capture output
                log_stream = StringIO()
                handler = logging.StreamHandler(log_stream)
                logger = logging.getLogger()
                logger.setLevel(logging.INFO)
                logger.addHandler(handler)
                
                # Parse MQXLIFF file
                st.session_state.processing_info["status"] = "Parsing MQXLIFF"
                status_text.info("Parsing MQXLIFF file...")
                status_metric.metric("Status", "Parsing")
                time_metric.metric("Time", f"{int(time.time() - start_time)}s")
                
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
                    st.session_state.processing_info["status"] = "Counting errors"
                    status_text.info("Counting errors...")
                    status_metric.metric("Status", "Counting")
                    time_metric.metric("Time", f"{int(time.time() - start_time)}s")
                    
                    for category in cat_list:
                        # Import the specific resolver
                        module_name = ERROR_CATEGORIES[category]['module']
                        module = importlib.import_module(module_name)
                        
                        if category == 'terminology':
                            errors = module.find_terminology_errors(mqxliff_dom, debug_mode)
                            category_total = len(errors)
                        elif category == 'consistency':
                            errors = module.find_consistency_errors(mqxliff_dom, debug_mode)
                            category_total = len(errors)
                        else:
                            category_total = 0
                            
                        total_stats['total'] += category_total
                        status_text.info(f"Found {category_total} {category} errors")
                    
                    st.session_state.processing_info["total_errors"] = total_stats['total']
                    progress_metric.metric("Progress", f"0/{total_stats['total']}")
                    
                    # Process each category with progress updates
                    if total_stats['total'] > 0:
                        processed_count = 0
                        st.session_state.processing_info["processed_count"] = 0
                        
                        for category in cat_list:
                            st.session_state.processing_info["status"] = f"Processing {category}"
                            status_text.info(f"Processing {category} errors...")
                            status_metric.metric("Status", f"Processing {category}")
                            
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
                                st.session_state.processing_info["current_unit"] = unit_id
                                st.session_state.processing_info["current_error"] = f"{i+1}/{len(errors)}"
                                
                                current_unit_text.info(f"Processing unit: {unit_id}")
                                current_error_text.info(f"Error {i+1}/{len(errors)} ({category})")
                                
                                # Display error details with colors
                                if category == 'terminology':
                                    term_info = error_info if error_info else module.extract_term_info(warning)
                                    source_term = term_info.get('source_term', '')
                                    target_suggestions = ', '.join(term_info.get('target_suggestions', []))
                                    
                                    st.session_state.processing_info["error_details"] = f"Term: {source_term} → {target_suggestions}"
                                    
                                    source_term_text.markdown(f"**Source Term:**\n<div style='background-color:#e6f3ff;padding:10px;border-radius:5px;'>{source_term}</div>", unsafe_allow_html=True)
                                    target_suggestions_text.markdown(f"**Target Suggestions:**\n<div style='background-color:#e6ffe6;padding:10px;border-radius:5px;'>{target_suggestions}</div>", unsafe_allow_html=True)
                                else:
                                    consistency_info = error_info
                                    consistent_text = consistency_info.get('consistent_text', '')
                                    inconsistent_text = consistency_info.get('inconsistent_text', '')
                                    
                                    st.session_state.processing_info["error_details"] = f"Consistent: {consistent_text} → Inconsistent: {inconsistent_text}"
                                    
                                    source_term_text.markdown(f"**Consistent Text:**\n<div style='background-color:#e6f3ff;padding:10px;border-radius:5px;'>{consistent_text}</div>", unsafe_allow_html=True)
                                    target_suggestions_text.markdown(f"**Inconsistent Text:**\n<div style='background-color:#ffe6e6;padding:10px;border-radius:5px;'>{inconsistent_text}</div>", unsafe_allow_html=True)
                                
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
                                
                                # Update progress bar and metrics
                                processed_count += 1
                                st.session_state.processing_info["processed_count"] = processed_count
                                st.session_state.processing_info["progress"] = processed_count / total_stats['total']
                                
                                progress_percentage = int((processed_count / total_stats['total']) * 100)
                                progress_bar.progress(processed_count / total_stats['total'])
                                progress_metric.metric("Progress", f"{processed_count}/{total_stats['total']} ({progress_percentage}%)")
                                time_metric.metric("Time", f"{int(time.time() - start_time)}s")
                                
                                # Update log display
                                log_output.text_area("Log Output", log_stream.getvalue(), height=200)
                                
                                # Add brief delay to allow UI updates
                                time.sleep(0.05)
                            
                            # Update total stats
                            total_stats['fixed'] += category_stats['fixed']
                            total_stats['ignored'] += category_stats['ignored']
                            
                            # Save intermediate results
                            if category_stats['fixed'] > 0 or category_stats['ignored'] > 0:
                                st.session_state.processing_info["status"] = f"Saving {category} changes"
                                status_text.info(f"Saving changes after processing {category} errors...")
                                status_metric.metric("Status", f"Saving {category}")
                                file_handler.save_file(mqxliff_dom, tmp_path)
                                
                            status_text.success(f"Completed {category}: {category_stats['fixed']} fixed, {category_stats['ignored']} ignored")
                    
                    # Ignore remaining errors if requested
                    if ignore_remaining:
                        st.session_state.processing_info["status"] = "Ignoring remaining"
                        status_text.info("Ignoring remaining errors...")
                        status_metric.metric("Status", "Ignoring remaining")
                        
                        ignored_count = file_handler.ignore_remaining_errors(
                            mqxliff_dom, 
                            processed_categories=[ERROR_CATEGORIES[c]['codes'] for c in cat_list]
                        )
                        status_text.info(f"Ignored {ignored_count} remaining errors")
                        total_stats['ignored'] += ignored_count
                        
                        # Save final changes
                        file_handler.save_file(mqxliff_dom, tmp_path)
                    
                    # Show results
                    st.session_state.processing_info["status"] = "Completed"
                    st.session_state.processing_info["progress"] = 1.0
                    
                    elapsed_time = int(time.time() - start_time)
                    progress_bar.progress(1.0)
                    status_metric.metric("Status", "Completed")
                    progress_metric.metric("Progress", "100%")
                    time_metric.metric("Time", f"{elapsed_time}s")
                    
                    status_text.success(f"Processing complete! Fixed {total_stats['fixed']} errors and ignored {total_stats['ignored']} errors in {elapsed_time} seconds.")
                    current_unit_text.empty()
                    current_error_text.empty()
                    source_term_text.empty()
                    target_suggestions_text.empty()
                    
                    # Provide download link for processed file
                    with open(tmp_path, "rb") as file:
                        processed_file = file.read()
                        
                    st.download_button(
                        label="Download Processed File",
                        data=processed_file,
                        file_name=uploaded_file.name,
                        mime="application/octet-stream"
                    )
                    
                    # Show complete logs
                    log_output.text_area("Complete Processing Logs", log_stream.getvalue(), height=300)
                        
            except Exception as e:
                st.session_state.processing_info["status"] = "Error"
                st.error(f"Error processing file: {str(e)}")
                import traceback
                st.text_area("Error Details", traceback.format_exc(), height=200)
                
                # Update metrics on error
                status_metric.metric("Status", "Error")
                time_metric.metric("Time", f"{int(time.time() - start_time)}s")
                
                # Log the error
                log_output.text_area("Error Logs", log_stream.getvalue(), height=300)
                
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