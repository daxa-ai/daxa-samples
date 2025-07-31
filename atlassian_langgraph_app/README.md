# Atlassian LangGraph Streamlit App

This Streamlit application provides a user-friendly interface to interact with Atlassian resources (JIRA, Confluence, etc.) using LangGraph and the Model Context Protocol (MCP).

## Features

- **Interactive UI**: Clean Streamlit interface with text input and final answer display
- **LangGraph Integration**: Uses LangGraph for complex workflow orchestration
- **MCP Support**: Connects to Atlassian MCP server for accessing JIRA, Confluence, and other Atlassian resources
- **Clean Output**: Shows only the final parsed answer, not intermediate steps
- **Error Handling**: Graceful error handling and user feedback
- **Modular Design**: Clean separation between LangGraph logic and UI components

## Prerequisites

1. **Atlassian MCP Server**: Must be running on `localhost:9003`
2. **OpenAI API Key**: Configured in the application
3. **Docker**: For running the MCP server container
4. **Python Dependencies**: Listed in `requirements.txt`

## Installation

1. **Clone or navigate to the project directory**:
   ```bash
   cd stack/examples/atlassian_langgraph_app
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the Atlassian MCP server** (in a separate terminal):
   ```bash
   # Example: Run the MCP server container
   docker run -p 9003:9003 your-mcp-atlassian-server
   ```

## Usage

1. **Run the Streamlit app**:
   ```bash
   streamlit run streamlit_app.py
   ```

2. **Open your browser** and navigate to the URL shown in the terminal (typically `http://localhost:8501`)

3. **Enter your query** in the text area. Examples:
   - "What is the status of JIRA ticket SMP-8?"
   - "Search for Confluence pages about API documentation"
   - "Get project information for Project ABC"

4. **Click "Submit Query"** to process your request

5. **View the final answer** in the response area

## File Structure

```
atlassian_langgraph_app/
├── streamlit_app.py          # Main Streamlit application (UI only)
├── mcp-langgraph-atlassian.py # LangGraph logic and MCP integration
├── requirements.txt          # Python dependencies
└── README.md                # This file
```

## Architecture

The application follows a clean modular design:

### `mcp-langgraph-atlassian.py`
- **`setup_langgraph()`**: Initializes and configures the LangGraph with MCP tools
- **`process_query()`**: Main function that processes user queries and returns final answer
- **`extract_final_answer()`**: Extracts the final parsed answer from the stream
- **`main()`**: Standalone execution function for testing

### `streamlit_app.py`
- **UI Components**: Streamlit interface elements
- **Session Management**: Handles response state and user interactions
- **Async Integration**: Safely calls the LangGraph functions from the UI

### Benefits of This Structure:
- **Separation of Concerns**: LangGraph logic is separate from UI code
- **Reusability**: The LangGraph module can be used independently
- **Maintainability**: Easier to update either the logic or UI independently
- **Testing**: Can test LangGraph functions separately from the UI
- **Clean Output**: Only shows the final parsed answer, not intermediate steps

## Configuration

### OpenAI API Key
The application uses a hardcoded OpenAI API key in `mcp-langgraph-atlassian.py`. For production use, consider:
- Using environment variables
- Streamlit secrets management
- Secure key management systems

### MCP Server URL
The app connects to `http://localhost:9003/mcp`. Modify the URL in `mcp-langgraph-atlassian.py` if your MCP server runs on a different port or host.

## Troubleshooting

### Common Issues

1. **MCP Server Connection Error**:
   - Ensure the Atlassian MCP server is running on port 9003
   - Check Docker container status
   - Verify network connectivity

2. **OpenAI API Errors**:
   - Verify your API key is valid
   - Check API quota and billing status
   - Ensure proper internet connectivity

3. **Streamlit Display Issues**:
   - Clear browser cache
   - Check Streamlit version compatibility
   - Restart the Streamlit server

4. **Import Errors**:
   - Ensure you're running from the correct directory
   - Check that all dependencies are installed
   - Verify the file structure is correct

### Debug Mode
To run in debug mode, add the `--debug` flag:
```bash
streamlit run streamlit_app.py --debug
```

## Development

### Adding New Features

1. **New MCP Tools**: Update the tool binding logic in `setup_langgraph()`
2. **UI Enhancements**: Modify components in `streamlit_app.py`
3. **Error Handling**: Enhance exception handling in `process_query()`
4. **Answer Parsing**: Update the `extract_final_answer()` function

### Testing the LangGraph Logic Separately

You can test the LangGraph functionality independently:
```bash
python mcp-langgraph-atlassian.py
```

This will run the example query and show the final parsed answer in the console.

## License

This project is part of the Proxima framework and follows the same licensing terms. 