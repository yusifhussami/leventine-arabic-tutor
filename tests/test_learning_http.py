import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from api import items, lessons
from lexicon import serve
from lexicon.cards import list_decks
from lexicon.load import connect
from lexicon.notebook import save_lesson


class HostedRoutes(serve.NotebookHandler):
    def do_GET(self):
        if self.path.startswith('/api/lessons'):
            lessons.handler.do_GET(self)
        elif self.path.startswith('/api/items'):
            items.handler.do_GET(self)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/lessons'):
            lessons.handler.do_POST(self)
        elif self.path.startswith('/api/items'):
            items.handler.do_POST(self)
        else:
            super().do_POST()


class LearningHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name)/'notebook.db'
        self.patch = patch.object(serve, 'DB_PATH', self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def request(self, port, path, payload=None):
        req = urllib.request.Request(f'http://127.0.0.1:{port}'+path, data=json.dumps(payload).encode() if payload is not None else None, headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def exercise(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            saved = self.request(server.server_port, '/api/lessons', {'action':'capture','title':'Grammar lesson','learned_on':'2026-11-16','words_text':'katab = write','rules':[{'title':'Continuous','explanation':'3am + imperfect'}]})
            task = self.request(server.server_port, '/api/lessons?action=task&id='+str(saved['task_id']))
            self.assertEqual(task['words'][0]['spelling'], 'katab')
            written = self.request(server.server_port, '/api/lessons', {'action':'attempt','task_id':task['id'],'revision':0,'text':'My own sentence'})
            self.request(server.server_port, '/api/lessons', {'action':'correction','attempt_id':written['attempt_id'],'text':'Teacher correction','author':'Teacher notes entered by me'})
            detail = self.request(server.server_port, '/api/lessons?action=task&id='+str(task['id']))
            self.assertEqual(detail['attempts'][0]['text'], 'My own sentence')
            self.assertEqual(detail['attempts'][0]['corrections'][0]['text'], 'Teacher correction')
            word_id = task['words'][0]['id']
            categories = self.request(server.server_port, '/api/items', {'action':'classify-word','item_id':word_id,'category':'adjective'})
            self.assertEqual(categories['assignments'][str(word_id)], 'adjective')
            self.assertEqual(self.request(server.server_port, '/api/items?action=word-classes')['assignments'][str(word_id)], 'adjective')
            found = self.request(server.server_port, '/api/items?action=dictionary&q=coffee')
            self.assertGreater(found['total'], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_local_api_flow(self):
        self.exercise(serve.NotebookHandler)

    def test_hosted_adapters_use_the_same_flow(self):
        def work(fn):
            conn = connect(self.path)
            try:
                return fn(conn)
            finally:
                conn.close()
        with patch.object(lessons, 'require_user', return_value='local'), patch.object(items, 'require_user', return_value='local'), patch.object(lessons, 'with_db', side_effect=work), patch.object(items, 'with_db', side_effect=work):
            self.exercise(HostedRoutes)

    def test_reading_words_preserves_duplicate_ids_and_card_progress(self):
        conn = connect(self.path)
        saved = save_lesson(conn, '2026-01-01', 'ahwe = coffee', embed=lambda rows:[None]*len(rows))
        list_decks(conn, 'local')
        conn.execute('UPDATE study_cards SET reps = 7, lapses = 2, stability = 12.5')
        conn.execute("INSERT INTO lesson_items(lesson_id,position,spelling,gloss,kind) VALUES (?,1,'ahwe','coffee','word')", (saved['id'],))
        conn.commit()
        before = [dict(row) for row in conn.execute('SELECT * FROM study_cards').fetchall()]
        conn.close()
        server = ThreadingHTTPServer(('127.0.0.1', 0), serve.NotebookHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            rows = self.request(server.server_port, '/api/items')
            self.assertEqual(len(rows), 2)
            conn = connect(self.path)
            self.assertEqual([dict(row) for row in conn.execute('SELECT * FROM study_cards').fetchall()], before)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
