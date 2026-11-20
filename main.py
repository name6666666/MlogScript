from pathlib import Path
from traceback import format_exc
from mlogscript import compile
from flask import Flask, request



app = Flask(__name__)

@app.route('/')
def main_route():
    return Path('index.html').read_text('utf-8')

@app.route('/compile', methods=['POST'])
def compile_route():
    text = request.get_data(as_text=True)
    try:
        res = compile(text, 'main.mls', copy=False)
    except Exception:
        return {'code': 1, 'message': format_exc()}
    return {'code': 0, 'data': res}
