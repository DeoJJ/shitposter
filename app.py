# app.py
from flask import Flask, render_template, request, Response, jsonify, url_for
from vk_logic import process_closed_walls, process_open_walls
import threading
import re
import sys
import json

app = Flask(__name__)

# Окремі буфери та прапори для кожного процесу
log_buffer_closed = []
log_buffer_open = []
stop_flag_closed = threading.Event()
stop_flag_open = threading.Event()


def extract_vk_access_token(url_or_token):
    match = re.search(r'#access_token=([^&]+)', url_or_token)
    if match:
        return match.group(1)
    return url_or_token


@app.route('/')
def index():
    try:
        return render_template('form.html')
    except Exception as e:
        print(f"Error rendering form.html: {e}", file=sys.stderr)
        return "Помилка завантаження сторінки. Перевірте логи сервера.", 500


def run_process(target, args):
    thread = threading.Thread(target=target, args=args)
    thread.daemon = True
    thread.start()


@app.route('/post_to_closed', methods=['POST'])
def post_to_closed():
    global log_buffer_closed
    log_buffer_closed.clear()
    stop_flag_closed.clear()

    data = request.get_json()
    token = extract_vk_access_token(data.get('token'))
    message = data.get('message')
    attachments = data.get('attachments', [])
    group_links = data.get('group_links', [])

    if not all([token, message, group_links]):
        return jsonify({"error": "Токен, повідомлення та посилання на групи є обов'язковими"}), 400

    run_process(process_closed_walls, (token, message, attachments, group_links, log_buffer_closed, stop_flag_closed))
    return jsonify({"status": "started"}), 202


@app.route('/post_to_open', methods=['POST'])
def post_to_open():
    global log_buffer_open
    log_buffer_open.clear()
    stop_flag_open.clear()

    data = request.get_json()
    token = extract_vk_access_token(data.get('token'))
    message = data.get('message')
    attachments = data.get('attachments', [])
    group_links = data.get('group_links', [])

    if not all([token, message, group_links]):
        return jsonify({"error": "Токен, повідомлення та посилання на групи є обов'язковими"}), 400

    run_process(process_open_walls, (token, message, attachments, group_links, log_buffer_open, stop_flag_open))
    return jsonify({"status": "started"}), 202


@app.route('/stop_closed', methods=['POST'])
def stop_closed():
    stop_flag_closed.set()
    return jsonify({"status": "stopping"})


@app.route('/stop_open', methods=['POST'])
def stop_open():
    stop_flag_open.set()
    return jsonify({"status": "stopping"})


def sse_stream(log_buffer, stop_flag):
    previous_length = 0
    while not stop_flag.is_set():
        if len(log_buffer) > previous_length:
            for line in log_buffer[previous_length:]:
                yield f"data: {line}\n\n"
            previous_length = len(log_buffer)

        if stop_flag.is_set():
            break

        threading.Event().wait(0.1)

    final_message = json.dumps({"type": "summary", "message": "Процес зупинено користувачем."})
    if not log_buffer or log_buffer[-1] != final_message:
        yield f"data: {final_message}\n\n"


@app.route('/stream_closed')
def stream_closed():
    return Response(sse_stream(log_buffer_closed, stop_flag_closed), mimetype='text/event-stream')


@app.route('/stream_open')
def stream_open():
    return Response(sse_stream(log_buffer_open, stop_flag_open), mimetype='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
