# Sri Lanka Flood Alert API - Backend

FastAPI-based REST API for Sri Lankan flood monitoring data.

## Features

- Real-time flood alerts
- Water level monitoring
- River basin information
- Station data management
- Auto-sync with government data sources

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python run.py
```

The API will be available at `http://localhost:8000`

## API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Endpoints

- `/api/alerts` - Flood alerts
- `/api/levels` - Water levels
- `/api/rivers` - River information
- `/api/basins` - Basin data
- `/api/stations` - Station information

## Deployment

Configured for Railway, Render, and Vercel deployments.
