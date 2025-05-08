# MemoQ QA Error Resolution Tool

A powerful tool for automatically detecting and resolving quality assurance errors in MemoQ MQXLIFF translation files using AI.

## Overview

This tool helps translators and translation project managers by:

1. Automatically detecting QA errors in MQXLIFF files
2. Using AI-powered suggestions to fix these errors
3. Supporting both interactive and automatic error resolution
4. Generating comprehensive reports on fixed and ignored errors

The tool currently handles these error types:
- **Terminology errors** (code: 03091) - Terms that should be translated according to your terminology database
- **Consistency errors** (codes: 03100, 03101) - Inconsistent translations of the same source text

## Features

- **AI-Powered Error Resolution**: Leverages OpenAI's models to analyze and suggest fixes for translation errors
- **Batch Processing**: Process multiple error types in a single run
- **Interactive Mode**: Review and choose how to handle each error
- **Automatic Mode**: Let AI decide how to fix errors without user intervention
- **Detailed Logging**: Comprehensive logs track all actions and decisions
- **Colored Output**: Makes it easier to distinguish between different error types and suggestions
- **Web Interface**: Optional Streamlit-based web interface for user-friendly operation

## Installation

### Requirements

- Python 3.6 or higher
- OpenAI API key

### Setup

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/memoq-qa-resolver.git
   cd memoq-qa-resolver
   ```

2. Install required packages:
   ```
   pip install openai streamlit
   ```

3. Set up your OpenAI API key:
   ```
   # In Windows PowerShell
   $env:OPENAI_API_KEY = "your-api-key-here"
   
   # On Linux/MacOS
   export OPENAI_API_KEY="your-api-key-here"
   ```

## Usage

### Command Line Interface

```
python qa_resolver.py --file your-file.mqxliff [options]
```

Options:
- `--file/-f`: Target MQXLIFF file (required)
- `--categories/-c`: Error categories to process (default: all)
- `--auto/-a`: Run in automatic mode without user interaction
- `--model/-m`: OpenAI model to use (default: gpt-4)
- `--debug/-d`: Enable debug logging
- `--ignore-remaining/-i`: Mark non-processed errors as ignored

Examples:
```bash
# Process all error types interactively
python qa_resolver.py --file translation.mqxliff

# Process only terminology errors
python qa_resolver.py --file translation.mqxliff --categories terminology

# Process automatically without user interaction
python qa_resolver.py --file translation.mqxliff --auto

# Use GPT-3.5 Turbo instead of GPT-4
python qa_resolver.py --file translation.mqxliff --model gpt-3.5-turbo
```

### Web Interface (Streamlit)

Launch the web interface:

```
streamlit run streamlitQA.py
```

Then follow the instructions in the web interface:
1. Enter your OpenAI API key in the sidebar
2. Upload an MQXLIFF file
3. Select error categories to process
4. Choose between automatic or interactive mode
5. Click 'Process File'
6. Download the processed file when complete

## GitHub & Streamlit Cloud Deployment

### Deploying to Streamlit Cloud

1. Push your code to GitHub:
   ```
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/yourusername/memoq-qa-resolver.git
   git push -u origin main
   ```

2. Go to [Streamlit Cloud](https://streamlit.io/cloud)
3. Sign in with your GitHub account
4. Click "New app" and select your repository
5. Configure the app:
   - Main file path: `streamlitQA.py`
   - Any required secrets (like API keys)
6. Deploy the app

Your app will be available at a URL like: `https://yourusername-memoq-qa-resolver-streamlitqa.streamlit.app`

### Repository Structure For Streamlit Cloud

```
memoq-qa-resolver/
├── streamlitQA.py        # Streamlit web interface
├── qa_resolver.py        # Main resolver script
├── analyze_mqxliff.py    # MQXLIFF analysis tool
├── .streamlit/           # Streamlit configuration
│   └── config.toml       # Streamlit settings
├── common/               # Common modules
│   ├── __init__.py       # Makes directory a package
│   ├── ai_handler.py     # AI integration
│   ├── file_handler.py   # File handling utilities
│   ├── report_handler.py # Report generation
│   └── utils.py          # Utility functions
├── resolvers/            # Error resolvers
│   ├── __init__.py       # Makes directory a package
│   ├── consistency_resolver.py  # Consistency errors
│   └── terminology_resolver.py  # Terminology errors
├── requirements.txt      # Dependencies
└── README.md             # Documentation
```

## Performance Considerations

When running on Streamlit Cloud:
- Processing may be slower compared to local execution due to server resource limitations
- For large files, consider processing locally or using the "Automatic Mode"
- The web interface provides detailed progress indicators to track processing status

## Troubleshooting

### Common Issues

1. **Module Import Errors**:
   - Ensure you have the correct directory structure
   - Use `python -m streamlit run streamlitQA.py` from the project root

2. **OpenAI API Issues**:
   - Verify your API key is set correctly
   - Check for usage limits or billing issues

3. **File Processing Errors**:
   - Verify your MQXLIFF file is valid and not corrupted
   - Try using the `analyze_mqxliff.py` tool to inspect the file structure

### Getting Help

- Check the logs for detailed error information
- Examine the `qa_resolver_*.log` files for debugging information
- Create an issue on the GitHub repository

## Extending the Tool

### Adding New Error Types

1. Create a new resolver module in the `resolvers` directory
2. Add the error category and codes to the `ERROR_CATEGORIES` dictionary in `qa_resolver.py`
3. Implement error detection and resolution logic
4. Update the web interface to support the new error type

## License

This tool is available under the MIT License.

## Acknowledgements

- This tool uses OpenAI's GPT models for error analysis and correction
- Built for use with MemoQ translation environment files
