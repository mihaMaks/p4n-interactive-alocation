import json
import os
from flask import Blueprint, request, jsonify

FORUM_FILE = os.path.join(os.path.dirname(__file__), '../../data/forum.json')
forum_api = Blueprint('forum_api', __name__)

def _read_forum():
    with open(FORUM_FILE, 'r') as f:
        return json.load(f)

def _write_forum(data):
    with open(FORUM_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@forum_api.route('/api/forum/messages', methods=['GET', 'POST'])
def messages():
    if request.method == 'GET':
        forum = _read_forum()
        return jsonify(success=True, data=forum['messages'][-50:])

    # POST
    forum = _read_forum()
    data = request.get_json(silent=True) or {}
    msg = {
        'animal_name': data.get('animal_name', 'Anonymous'),
        'text': data.get('text', '').strip(),
        'ts': data.get('ts'),
    }
    if not msg['text']:
        return jsonify(success=False, error='Empty message'), 400
    forum['messages'].append(msg)
    _write_forum(forum)
    return jsonify(success=True, data=msg)