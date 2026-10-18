import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import i18n
import cli
from main import create_app
from auth_helper import sign_in

HANGUL = re.compile('[가-힣]')


def backend_messages():
    """Korean texts in the engine: plain strings and f-strings with numbered placeholders, docstrings and scripts excluded."""
    found = set()
    for path in BACKEND.glob('*.py'):
        if path.name == 'i18n.py':
            continue
        tree = ast.parse(path.read_text('utf-8'))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                parts, index = [], 0
                for value in node.values:
                    if isinstance(value, ast.Constant):
                        parts.append(str(value.value))
                    else:
                        parts.append(f'{{{index}}}')
                        index += 1
                text = ''.join(parts)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and not isinstance(parents.get(node), (ast.JoinedStr, ast.Expr)):
                text = node.value
            else:
                continue
            if HANGUL.search(text) and '$' not in text:
                found.add(text)
    return found


class TranslationTests(unittest.TestCase):
    def test_every_engine_message_has_english(self):
        known = set(i18n.EN) | set(i18n.SYSTEM)
        # Messages built from several pieces are matched by their full template at runtime.
        partial = {'{0}\n시작한 구성의 종료 상태를 확인해 주세요: ', '\n[{0}] {1}\n'}
        missing = sorted(text for text in backend_messages() - known - partial if not text.startswith('\n['))
        self.assertEqual(missing, [])

    def test_templates_translate_values_too(self):
        text = 'API: 원격 시작 명령이 실패했습니다.\n종료 코드 3'
        self.assertEqual(i18n.translate(text, 'en'), 'API: the remote start command failed.\nExit code 3')
        self.assertEqual(i18n.translate('Value error, 한 줄로 입력해 주세요.', 'en'), 'Value error, Enter it on one line.')
        self.assertEqual(i18n.translate('그대로 둡니다', 'en'), '그대로 둡니다')
        self.assertEqual(i18n.translate('서비스를 찾을 수 없습니다.', 'ko'), '서비스를 찾을 수 없습니다.')

    def test_payload_keeps_user_data(self):
        payload = {'services': [{'name': '시작', 'message': '응답을 확인하고 있습니다.'}], 'detail': '로그인해 주세요.'}
        self.assertEqual(i18n.translate_payload(payload, 'en'),
                         {'services': [{'name': '시작', 'message': 'Waiting for a response.'}], 'detail': 'Please sign in.'})

    def test_language_choice(self):
        self.assertEqual(i18n.request_lang({'x-stackpad-lang': 'en', 'accept-language': 'ko-KR'}), 'en')
        self.assertEqual(i18n.request_lang({'accept-language': 'ko-KR,ko;q=0.9'}), 'ko')
        self.assertEqual(i18n.request_lang({'accept-language': 'de-DE'}), 'en')

    def test_api_answers_in_the_requested_language(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder, folder)
            client = TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 50000))
            self.assertEqual(client.get('/api/services', headers={'X-StackPad-Lang': 'en'}).json()['detail'], 'Please sign in.')
            self.assertEqual(client.get('/api/services', headers={'X-StackPad-Lang': 'ko'}).json()['detail'], '로그인해 주세요.')
            self.assertEqual(client.post('/api/logout', headers={'Origin': 'https://evil.example', 'Accept-Language': 'en-US'}).json()['detail'],
                             'Send the request from the StackPad screen.')
            sign_in(app, client)
            response = client.delete('/api/pads/missing', headers={'Origin': 'http://127.0.0.1', 'X-StackPad-Lang': 'en'})
            self.assertEqual((response.status_code, response.json()['detail']), (404, 'Service not found.'))


if __name__ == '__main__':
    unittest.main()
