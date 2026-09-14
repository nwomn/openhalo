"""HTTP contract checks without starting the camera or model."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from demo import Demo, handler_for


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.demo=Demo(Path(self.temp.name),600)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.demo))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_idle_page_and_state_do_not_start_camera(self):
        self.assertIn('Qwen'.encode(),urlopen(self.url).read())
        self.assertIn(b'"active": false',urlopen(self.url+'/api/state').read())
        self.assertIsNone(self.demo.thread)

    def test_foreign_origin_cannot_start_camera(self):
        request=Request(self.url+'/api/start',method='POST',headers={'Origin':'http://other.example'})
        with self.assertRaises(HTTPError) as raised:
            urlopen(request)
        self.assertEqual(raised.exception.code,403)
        self.assertIsNone(self.demo.thread)

    def test_invalid_sample_does_not_read_arbitrary_files(self):
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.url+'/sample.jpg?run=../../etc&batch=-1&index=-1')
        self.assertEqual(raised.exception.code,404)


if __name__=='__main__':
    unittest.main()
