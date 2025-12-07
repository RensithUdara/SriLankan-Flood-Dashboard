# Sri Lanka Flood Alert Dashboard - Frontend

Interactive web dashboard for monitoring flood alerts and water levels in Sri Lanka.

## Features

- Real-time flood alert visualization
- Interactive map with station locations
- Water level charts and trends
- Basin and river monitoring
- Responsive design

## Setup

1. Open `index.html` in a web browser, or
2. Use a local server:

```bash
# Python
python -m http.server 8080

# Node.js
npx http-server -p 8080
```

## Configuration

Update the API endpoint in `index.html`:

```javascript
const API_BASE_URL = 'http://localhost:8000/api';  // Change to your API URL
```

## Usage

The dashboard automatically fetches data from the backend API and displays:
- Flood alerts with severity levels
- Water level monitoring
- Station information
- River and basin data
