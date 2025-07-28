# pj-cdc-ecommerce

## Development

```
# Python Environment
make setup-venv      # Setup virtual environment
make activate-venv   # Show activation command
make install-deps    # Install dependencies
make clean-venv      # Remove venv
```

```
# Local Development  
make run-ui-local    # Run Streamlit locally (requires active venv)
make demo-data       # Generate test data (requires active venv)

# Docker Deployment
make up-ui           # Start UI as Docker service
make build-ui        # Build Docker image
```
