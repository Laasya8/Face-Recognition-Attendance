"""WSGI entry point.

Serve in production with:      waitress-serve --listen=0.0.0.0:8000 run:app
Run the Flask CLI with:        flask --app run.py <command>
Run the debug server with:     python run.py
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
