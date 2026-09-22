#!/usr/bin/env python3
"""Unit tests for tools/ingest.py (offline: no network, no writes to the project).

The loader script writes straight into the live knowledge base, so its chunking and its
credential handling are the two places where a mistake is expensive: a bad chunk boundary
silently drops text, and a wrong key makes the embedding call fail late, after deletions.
Both are covered here.

  python tests/test_ingest.py     -> prints PASS/FAIL per case, exit code 1 on any failure
"""

import importlib.util
import json
import os
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = []
TMP = tempfile.mkdtemp(prefix='ingest-tests-')


def load_module():
    spec = importlib.util.spec_from_file_location('ingest', os.path.join(ROOT, 'tools', 'ingest.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(cid, desc, ok, detail=''):
    RESULTS.append({'id': cid, 'description': desc, 'status': 'PASS' if ok else 'FAIL',
                    'detail': str(detail)[:200]})
    print('  %-4s %-6s %s%s' % ('PASS' if ok else 'FAIL', cid, desc,
                                ('  [' + str(detail)[:90] + ']') if detail else ''))


def write(name, text, newline=None):
    path = os.path.join(TMP, name)
    with open(path, 'w', encoding='utf-8', newline=newline) as fh:
        fh.write(text)
    return path


def main():
    ingest = load_module()
    print('INGEST UNIT TESTS')
    print('=' * 78)

    # --- chunking: structure and boundaries
    small = write('small.md', '# Title\n\nFirst block.\n\nSecond block.\n')
    chunks = ingest.chunk_file(small)
    check('T1.1', 'a small file becomes one chunk with its line range',
          len(chunks) == 1 and chunks[0]['from'] == 1 and chunks[0]['to'] == 6,
          'chunks=%d loc=%s' % (len(chunks), chunks[0] if chunks else None))

    big_block = write('big.md', 'x' * (ingest.CHUNK_CHARS * 3) + '\n')
    chunks = ingest.chunk_file(big_block)
    check('T1.2', 'a single oversized block is split, not truncated',
          len(chunks) >= 3 and all(len(c['content']) <= ingest.CHUNK_CHARS for c in chunks),
          'chunks=%d max=%d' % (len(chunks), max(len(c['content']) for c in chunks)))

    many = write('many.md', '\n\n'.join('block %d of the document' % i for i in range(200)) + '\n')
    chunks = ingest.chunk_file(many)
    total_lines = len(open(many, encoding='utf-8').read().split('\n'))
    check('T1.3', 'no chunk exceeds the character limit',
          all(len(c['content']) <= ingest.CHUNK_CHARS for c in chunks),
          'chunks=%d max=%d' % (len(chunks), max(len(c['content']) for c in chunks)))
    check('T1.4', 'every line of the document ends up in some chunk',
          chunks[0]['from'] == 1 and chunks[-1]['to'] == total_lines,
          'first=%s last=%s file_lines=%s' % (chunks[0]['from'], chunks[-1]['to'], total_lines))
    check('T1.5', 'chunk line ranges never go backwards',
          all(a['from'] <= b['from'] for a, b in zip(chunks, chunks[1:])),
          '%d chunks' % len(chunks))

    empty = write('empty.md', '\n\n   \n')
    check('T1.6', 'a whitespace-only file produces no chunks',
          ingest.chunk_file(empty) == [], ingest.chunk_file(empty))

    crlf = write('crlf.md', '# Title\r\n\r\nBlock one.\r\n\r\nBlock two.\r\n', newline='')
    check('T1.7', 'a CRLF file chunks without raising',
          len(ingest.chunk_file(crlf)) == 1, '%d chunks' % len(ingest.chunk_file(crlf)))

    # --- credential handling: the two APIs must not share headers
    secrets = {'supabaseUrl': 'https://example.supabase.co', 'serviceKey': 'SUPABASE_KEY',
               'siliconflowUrl': 'https://api.siliconflow.cn/v1', 'siliconflowKey': 'EMBED_KEY'}
    sb = ingest._supabase_headers(secrets)
    em = ingest._embedding_headers(secrets)
    check('T2.1', 'Supabase headers carry both apikey and Authorization',
          sb.get('apikey') == 'SUPABASE_KEY' and sb.get('Authorization') == 'Bearer SUPABASE_KEY',
          'keys=%s' % sorted(sb))
    check('T2.2', 'the embedding call uses the embedding key, not the service key',
          em.get('Authorization') == 'Bearer EMBED_KEY' and 'apikey' not in em,
          'keys=%s' % sorted(em))
    check('T2.3', 'no header builder leaks the service key into the embedding request',
          'SUPABASE_KEY' not in json.dumps(em), 'headers=%s' % sorted(em))

    # --- a dry run must not touch the network
    original = urllib.request.urlopen

    def explode(*a, **k):
        raise AssertionError('the network was called during --dry-run')

    urllib.request.urlopen = explode
    try:
        argv = sys.argv
        sys.argv = ['ingest.py', '--dry-run', '--dir', os.path.join(ROOT, 'knowledge')]
        rc = ingest.main()
        sys.argv = argv
    except AssertionError as exc:
        rc = 'network: %s' % exc
    finally:
        urllib.request.urlopen = original
    check('T3.1', '--dry-run exits 0 without any network call', rc == 0, 'returned %r' % rc)

    # --- a secrets file with a missing field must fail loudly, not half-work
    bad = write('secrets-bad.json', json.dumps({'supabaseUrl': 'https://x', 'serviceKey': 'k'}))
    try:
        ingest.read_secrets(bad)
        ok, detail = False, 'no error raised'
    except SystemExit as exc:
        # read_secrets checks the fields in order, so the first missing one wins: accept any
        # of them as long as the message names it instead of failing later with a raw KeyError
        message = str(exc)
        ok = ('siliconflowUrl' in message or 'siliconflowKey' in message)
        detail = message
    check('T3.2', 'a secrets file missing a field is refused with the field name', ok, detail)

    good = write('secrets-good.json', json.dumps({
        'supabaseUrl': 'https://x.supabase.co/', 'serviceKey': 'k',
        'siliconflowUrl': 'https://api.siliconflow.cn/v1/', 'siliconflowKey': 'e'}))
    loaded = ingest.read_secrets(good)
    check('T3.3', 'trailing slashes are stripped from both base URLs',
          loaded['supabaseUrl'] == 'https://x.supabase.co'
          and loaded['siliconflowUrl'] == 'https://api.siliconflow.cn/v1',
          '%s | %s' % (loaded['supabaseUrl'], loaded['siliconflowUrl']))

    failed = [r for r in RESULTS if r['status'] == 'FAIL']
    with open(os.path.join(HERE, 'ingest-results.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULTS, fh, indent=1)
    print('-' * 78)
    print('INGEST UNIT: %d cases, %d failed' % (len(RESULTS), len(failed)))
    print('RESULT: %s' % ('ALL PASS' if not failed else '%d FAILURE(S)' % len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
