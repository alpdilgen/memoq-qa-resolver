# MemoQ QA Error Resolution Tool

A tool for automatically detecting and resolving quality assurance errors in MemoQ MQXLIFF translation files using AI.

## What It Does

This tool helps translators and translation project managers by:

1. Automatically detecting QA errors in MQXLIFF files
2. Using AI to suggest fixes for these errors
3. Supporting both interactive and automatic error resolution
4. Generating reports on fixed and ignored errors

The tool handles these error types:
- **Terminology errors** (code: 03091) - Missing terms from your terminology database
- **Consistency errors** (codes: 03100, 03101) - Inconsistent translations of the same source text

## Features

- **AI-Powered Error Resolution**: Uses OpenAI's models to analyze and suggest fixes
- **Interactive Mode**: Review and choose how to handle each error
- **Automatic Mode**: Let AI decide how to fix errors without user interaction
- **Detailed Logging**: Tracks all actions and decisions
- **Colored Output**: Makes it easier to see different error types and suggestions

## How to Use

### Web Interface

1. Enter your OpenAI API key in the sidebar
2. Upload your MQXLIFF file
3. Select which error categories to process (terminology, consistency, or both)
4. Choose between automatic or interactive mode
5. Click 'Process File'
6. Monitor the progress bar and status updates
7. Download the processed file when complete

### Command Line

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
```

## Requirements

- OpenAI API key
- Internet connection (for AI integration)

## Troubleshooting

- If processing is slow, try using a smaller file or using automatic mode
- For OpenAI API issues, verify your API key is valid and has available credits
- If you encounter errors, check the logs shown at the bottom of the screen
