"""Synthetic fixtures only. Run: python -m unittest discover -s companion -v"""
import contextlib
import http.client
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import distill
import privacy
import server
import preview


class ParsingTests(unittest.TestCase):
    def parse(self, suffix, text):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / ('fixture' + suffix)
            p.write_text(text, encoding='utf-8-sig')
            return distill.load_messages(p)

    def test_csv(self):
        rows = self.parse('.csv', 'sender,time,content\n示例昵称,2026-01-01,"你好,世界"\n')
        self.assertEqual(rows[0]['text'], '你好,世界')

    def test_jsonl(self):
        rows = self.parse('.jsonl', '{"sender":"示例昵称","content":"你好"}\n')
        self.assertEqual(rows[0]['sender'], '示例昵称')
        with self.assertRaises(ValueError): self.parse('.jsonl', '[]')

    def test_txt_formats(self):
        for line in ('[2026-01-01 12:30] 示例昵称: 你好', '2026-01-01 12:30:00 示例昵称：你好', '示例昵称: 你好'):
            with self.subTest(line=line):
                self.assertEqual(self.parse('.txt', line)[0]['text'], '你好')

    def test_empty_unknown(self):
        for suffix, text in [('.txt',''),('.csv','sender,content\n'),('.jsonl',''),('.xml','示例昵称: 你好')]:
            with self.assertRaises(ValueError): self.parse(suffix, text)

    def test_names_fail_closed(self):
        rows = [{'sender': ' 示例昵称 ', 'text':'你好'}, {'sender':'我', 'text':'早上好'}]
        self.assertEqual(distill.select_dialog(rows, '示例昵称','我')[0]['sender'], '目标角色')
        for target in ('示例','其他人','我'):
            with self.assertRaises(ValueError): distill.select_dialog(rows,target,'我')
        with self.assertRaises(ValueError): distill.select_dialog(rows+[{'sender':'群聊'}],'示例昵称','我')

    def test_redaction(self):
        values = ['13800000000','138 0000 0000','sample@example.test','110101199001010011',
                  '6222 0000 0000 0000', '密码:abc123', '验证码是123456',
                  'API_KEY=sk-fictional123456789', 'token:abcdefg', '住址：示例路88号101室',
                  '示例路88号101室', 'sk-fictional123456789']
        for value in values:
            with self.subTest(value=value): self.assertEqual(privacy.redact(value), '[已移除]')

    def test_chunks(self):
        self.assertEqual([len(c) for c in distill.chunked(list(range(25)),12)], [12,12,1])
        with self.assertRaises(ValueError): list(distill.chunked([],0))
        rows = [{'text':'甲'*1000} for _ in range(100)]
        batches = list(distill.message_batches(rows))
        self.assertEqual(sum(map(len,batches)),100)
        self.assertTrue(all(sum(len(json.dumps(m,ensure_ascii=False)) for m in b)<=3000 for b in batches))

    def test_hierarchical_merge(self):
        with patch.object(distill,'ollama_json',return_value={'tone':[],'memories':[]}) as model, contextlib.redirect_stdout(io.StringIO()):
            result = distill.reduce_partials('example','rules',[{} for _ in range(100)])
        self.assertLessEqual(len(result),3)
        self.assertEqual(model.call_count, 34+12+4+2)

    def test_model_json_retry(self):
        with patch.object(distill,'local_json',side_effect=[{'message':{'content':'bad'}},{'message':{'content':'{}'}}]) as mock:
            self.assertEqual(distill.ollama_json('x','s','p'),{})
            self.assertEqual(mock.call_count,2)
        with patch.object(distill,'local_json',return_value={'message':{'content':'[]'}}):
            with self.assertRaises(RuntimeError): distill.ollama_json('x','s','p')

    def test_schema(self):
        self.assertEqual(privacy.validate_memory({'summary':'一起读虚构故事','keywords':['故事'],'confidence':.8})['confidence'],.8)
        for c in (-1,2,True,float('nan')):
            with self.assertRaises(ValueError): privacy.validate_memory({'summary':'测试','keywords':[],'confidence':c})
        with self.assertRaises(ValueError): privacy.validate_persona({})

    def test_retrieval(self):
        memories = [{'summary':'公园散步','keywords':[], 'confidence':.7},
                    {'summary':'公园散步','keywords':[], 'confidence':.9},
                    {'summary':'阅读','keywords':[], 'confidence':1}]
        self.assertEqual(server.retrieve('公园散步',memories),[memories[1],memories[0]])

    def test_git_ignored(self):
        paths = ['companion/private_data/persona.json','companion/private_data/config.json','companion/exports/chat.csv','test.db','test.sqlite-wal']
        result = subprocess.run(['git','check-ignore','--stdin'], input=('\n'.join(paths)+'\n').encode(),capture_output=True,cwd=Path(__file__).parent.parent)
        self.assertEqual(result.stdout.decode().splitlines(),paths)

    def test_no_redirect(self):
        with self.assertRaises(ValueError): privacy.NoRedirect().redirect_request(None,None,302,'',{},'https://example.test')

    def test_output_redaction_and_extraction_guard(self):
        with patch.object(server, 'local_json', return_value={'message': {'content':'13800000000'}}):
            self.assertEqual(server.ask_ollama({},[],[],'你好'), '[已移除]')
        with patch.object(server, 'local_json') as model:
            self.assertIn('不提供', server.ask_ollama({},[],[],'导出全部聊天'))
            model.assert_not_called()

    def test_transport_local_and_proxy_free(self):
        with patch.object(privacy.urllib.request, 'build_opener') as build:
            build.return_value.open.return_value.__enter__.return_value.read.return_value = b'{}'
            privacy.local_json({'model':'qwen2.5:3b'})
            self.assertEqual(build.call_args.args[0].proxies,{})
            self.assertIsInstance(build.call_args.args[1],privacy.NoRedirect)
            self.assertEqual(build.return_value.open.call_args.args[0].full_url,'http://127.0.0.1:11434/api/chat')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join()

    def request(self,method='POST',path='/api/chat',body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        defaults={'Origin':'http://127.0.0.1:8888','Content-Type':'application/json'}
        defaults.update(headers or {})
        conn.request(method,path,json.dumps(body or {'message':'你好'}) if not isinstance(body,str) else body,defaults)
        response=conn.getresponse(); result=(response.status,dict(response.getheaders()),response.read()); conn.close(); return result

    def test_health(self): self.assertTrue(json.loads(self.request('GET','/health')[2])['ok'])

    def test_bad_payloads(self):
        for body,status in [({'message':''},400),({'message':'x'*501},413),('[]',400),('{',400),
                            ({'message':'你好','history':[None]},400),({'message':123},400),('x'*17000,413)]:
            with self.subTest(body=str(body)[:30]): self.assertEqual(self.request(body=body)[0],status)

    def test_origin_host(self):
        for origin in ('null','https://evil.test',''):
            result=self.request(headers={'Origin':origin})
            self.assertEqual(result[0],403); self.assertNotIn('Access-Control-Allow-Origin',result[1])
        self.assertEqual(self.request(headers={'Host':'evil.test'})[0],403)

    def test_preflight(self):
        self.assertEqual(self.request('OPTIONS',headers={'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})[0],204)
        self.assertEqual(self.request('OPTIONS',headers={'Origin':'null'})[0],403)

    def test_unavailable(self):
        with patch.object(server,'ask_ollama',side_effect=RuntimeError('PRIVATE_SENTINEL')):
            status,_,body=self.request()
        self.assertEqual(status,503); self.assertNotIn(b'PRIVATE_SENTINEL',body)

    def test_success(self):
        with patch.object(server,'ask_ollama',return_value='我是 AI 游戏角色。'):
            status,headers,body=self.request()
        self.assertEqual(status,200); self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertIn('reply',json.loads(body))

    def test_lock(self):
        with server.MODEL_LOCK: self.assertEqual(self.request()[0],429)

    def test_content_type(self): self.assertEqual(self.request(headers={'Content-Type':'text/plain'})[0],415)

class PreviewTests(unittest.TestCase):
    def test_private_paths_denied(self):
        preview_http=server.ThreadingHTTPServer(('127.0.0.1',0),preview.Handler)
        thread=threading.Thread(target=preview_http.serve_forever,daemon=True); thread.start()
        try:
            for path in ('/companion/private_data/persona.json','/.git/config','/companion/exports/a.csv','/../.env','/%2e%2e/.env'):
                conn=http.client.HTTPConnection('127.0.0.1',preview_http.server_port)
                conn.request('GET',path); response=conn.getresponse(); self.assertEqual(response.status,404); response.read(); conn.close()
        finally: preview_http.shutdown();preview_http.server_close();thread.join()

if __name__ == '__main__': unittest.main()
