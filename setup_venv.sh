#!/bin/bash

# Python Virtual Environment Setup for CDC Project (Root Level)

VENV_DIR="venv"
PYTHON_VERSION="python3"
# Get the directory where this script is located (should be project root)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🐍 Setting up Python Virtual Environment for CDC Project..."
echo "📁 Project root: $PROJECT_ROOT"

cd "$PROJECT_ROOT"

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: requirements.txt not found in project root: $PROJECT_ROOT"
    echo "📁 Current directory contents:"
    ls -la
    exit 1
fi

# Check if Python is installed
if ! command -v $PYTHON_VERSION &> /dev/null; then
    echo "❌ Error: Python 3 is not installed or not in PATH"
    echo "   Please install Python 3.9+ first"
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Remove existing venv if exists
if [ -d "$VENV_DIR" ]; then
    echo "🗑️ Removing existing virtual environment..."
    rm -rf "$VENV_DIR"
fi

# Create virtual environment
echo "📦 Creating virtual environment in project root..."
$PYTHON_VERSION -m venv "$VENV_DIR"

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to create virtual environment"
    exit 1
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies from requirements.txt..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to install dependencies"
    exit 1
fi

echo ""
echo "✅ Virtual environment setup completed!"
echo ""
echo "📋 To use the virtual environment:"
echo "   source venv/bin/activate    # Activate"
echo "   deactivate                  # Deactivate"
echo ""
echo "🚀 To run the CDC Testing UI:"
echo "   source venv/bin/activate"
echo "   cd application/cdc-testing-ui"
echo "   streamlit run app.py"
