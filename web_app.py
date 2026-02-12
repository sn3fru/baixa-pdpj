"""
Devedor360 v2 - Entry point do servidor web.

Uso:
    python web_app.py
    # ou
    uvicorn web_app:app --reload --host 0.0.0.0 --port 8000
"""

import uvicorn
from web import app

if __name__ == "__main__":
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)
