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
from qa_resolver import process_category, get_categories_to_process

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
        with st.spinner("Processing your file..."):
            try:
                # Set up logging to capture output
                log_stream = StringIO()
                handler = logging.StreamHandler(log_stream)
                logger = logging.getLogger()
                logger.setLevel(logging.INFO)
                logger.addHandler(handler)
                
                # Parse MQXLIFF file
                mqxliff_dom = file_handler.parse_file(tmp_path)
                if not mqxliff_dom:
                    st.error("Failed to parse the MQXLIFF file.")
                else:
                    # Process each category
                    total_stats = {'fixed': 0, 'ignored': 0}
                    cat_list = get_categories_to_process(",".join(categories))
                    
                    # Create args object to pass to process_category
                    class Args:
                        pass
                    args = Args()
                    args.auto = auto_mode
                    args.model = model
                    args.debug = debug_mode
                    
                    for category in cat_list:
                        st.write(f"Processing {category} errors...")
                        category_stats = process_category(category, mqxliff_dom, args)
                        total_stats['fixed'] += category_stats['fixed']
                        total_stats['ignored'] += category_stats['ignored']
                        
                        # Save intermediate results
                        if category_stats['fixed'] > 0 or category_stats['ignored'] > 0:
                            file_handler.save_file(mqxliff_dom, tmp_path)
                    
                    # Ignore remaining errors if requested
                    if ignore_remaining:
                        from qa_resolver import ERROR_CATEGORIES
                        ignored_count = file_handler.ignore_remaining_errors(
                            mqxliff_dom, 
                            processed_categories=[ERROR_CATEGORIES[c]['codes'] for c in cat_list]
                        )
                        st.write(f"Ignored {ignored_count} remaining errors")
                        total_stats['ignored'] += ignored_count
                        
                        # Save final changes
                        file_handler.save_file(mqxliff_dom, tmp_path)
                    
                    # Show results
                    st.success(f"Processing complete! Fixed {total_stats['fixed']} errors and ignored {total_stats['ignored']} errors.")
                    
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
