#!/bin/bash
# Start both backend and frontend servers

echo "🚀 Starting Data Report Generator..."
echo ""

# Check if .env exists
if [ ! -f "backend/.env" ]; then
    echo "⚠️  backend/.env not found. Copying from .env.example..."
    cp backend/.env.example backend/.env
    echo "   Please edit backend/.env with your LLM API credentials."
    echo ""
fi

# Install dependencies if needed
if [ ! -d "backend/__pycache__" ]; then
    echo "📦 Installing backend dependencies..."
    pip3 install -r backend/requirements.txt
fi

if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd frontend && npm install && cd ..
fi

# Generate sample data if needed
if [ ! -f "sample_data.xlsx" ]; then
    echo "📊 Generating sample data..."
    cd backend && python3 create_sample_data.py && cd ..
fi

echo ""
echo "🔧 Starting backend (port 8000)..."
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

echo "🌐 Starting frontend (port 3001)..."
cd frontend && npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Both servers starting..."
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3001"
echo ""
echo "Press Ctrl+C to stop both servers"

# Trap Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
