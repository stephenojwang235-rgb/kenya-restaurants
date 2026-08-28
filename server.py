from flask import Flask, render_template
import os

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'

    if debug:
        print("Starting Flask development server...", flush=True)
        app.run(debug=True, port=port, host='0.0.0.0')
    else:
        print(f"Starting Waitress production server on port {port}...", flush=True)
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=4)