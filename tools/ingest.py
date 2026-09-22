#!/usr/bin/env python3
"""Load the knowledge base into Supabase with a real source label on every chunk.

Why this exists next to the n8n form uploader: n8n 2.38.7's Default Data Loader hardcodes
`metadata.source = "blob"` for binary input, and the node has no metadata parameter, so
documents uploaded through the workflow form cannot be traced back to a file name. This
script does the same job with the labels the answers need.

It chunks each markdown file, embeds the chunks with the same model the workflow uses
(BAAI/bge-m3, 1024 dimensions, SiliconFlow), and inserts rows into the `documents` table
with `metadata = {source, loc, blobType}`.

Credentials come from a local JSON file (never from this file, never from the command line):

    { "supabaseUrl": "https://<project>.supabase.co",
      "serviceKey": "<service role key>",
      "siliconflowUrl": "https://api.siliconflow.cn/v1",
      "siliconflowKey": "<key>" }

Usage:
    python tools/ingest.py --dry-run                     # show the plan, touch nothing
    python tools/ingest.py --replace                     # re-ingest every file in knowledge/
    python tools/ingest.py --replace knowledge/faq.md    # re-ingest one file

Exit code 0 = every file was stored, 1 = something failed (nothing is deleted unless the
embeddings for that file were obtained first).
"""

import argparse
import glob
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CHUNK_CHARS = 900
EMBED_MODEL = 'BAAI/bge-m3'
EXPECTED_DIM = 1024
USER_AGENT = 'rag-support-bot-ingest/1.0'
DEFAULT_SECRETS = os.environ.get('INGEST_SECRETS', r'D:\Tools\n8n\demo-secrets.json')


def read_secrets(path):
    if not os.path.exists(path):
        sys.exit('secrets file not found: %s (pass --secrets, or set INGEST_SECRETS)' % path)
    with open(path, encoding='utf-8') as fh:
        s = json.load(fh)
    for key in ('supabaseUrl', 'serviceKey', 'siliconflowUrl', 'siliconflowKey'):
        if not s.get(key):
            sys.exit('secrets file %s has no "%s"' % (path, key))
    s['supabaseUrl'] = s['supabaseUrl'].rstrip('/')
    s['siliconflowUrl'] = s['siliconflowUrl'].rstrip('/')
    return s


def chunk_file(path):
    """Split a markdown file into chunks of at most CHUNK_CHARS, keeping line numbers.

    Blank-line separated blocks form the natural unit, so a chunk never cuts a table or a
    paragraph in half unless the block itself is oversized.
    """
    with open(path, encoding='utf-8') as fh:
        lines = fh.read().split('\n')
    blocks, cur, start = [], [], 1
    for i, line in enumerate(lines, 1):
        if not cur:
            start = i
        cur.append(line)
        if line.strip() == '':
            blocks.append((start, i, cur))
            cur = []
    if cur:
        blocks.append((start, len(lines), cur))

    chunks, buf, buf_start, buf_end = [], [], None, None
    for b_start, b_end, b_lines in blocks:
        text = '\n'.join(b_lines)
        # an oversized single block is split on its own, so nothing silently exceeds the limit
        while len(text) > CHUNK_CHARS:
            if buf:
                chunks.append((buf_start, buf_end, '\n'.join(buf)))
                buf, buf_start, buf_end = [], None, None
            head, text = text[:CHUNK_CHARS], text[CHUNK_CHARS:]
            chunks.append((b_start, b_start, head))
        if buf and len('\n'.join(buf)) + len(text) > CHUNK_CHARS:
            chunks.append((buf_start, buf_end, '\n'.join(buf)))
            buf, buf_start, buf_end = [], None, None
        if not buf:
            buf_start = b_start
        buf.append(text)
        buf_end = b_end
    if buf:
        chunks.append((buf_start, buf_end, '\n'.join(buf)))
    return [{'content': c.strip(), 'from': a, 'to': b} for a, b, c in chunks if c.strip()]


def _supabase_headers(secrets, extra=None):
    # Supabase wants the service key in BOTH headers (the apikey header is what it checks
    # first; a bearer-only request is answered 401 "No API key found in request").
    headers = {
        'apikey': secrets['serviceKey'],
        'Authorization': 'Bearer ' + secrets['serviceKey'],
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
        'Prefer': 'return=minimal',
    }
    if extra:
        headers.update(extra)
    return headers


def _embedding_headers(secrets):
    return {
        'Authorization': 'Bearer ' + secrets['siliconflowKey'],
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
    }


def post(url, payload, headers, method='POST'):
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                 headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.status, resp.read().decode('utf-8', 'replace')


def delete(url, secrets):
    req = urllib.request.Request(url, headers=_supabase_headers(secrets), method='DELETE')
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status


def embed(texts, secrets):
    status, body = post(secrets['siliconflowUrl'] + '/embeddings',
                        {'model': EMBED_MODEL, 'input': texts},
                        _embedding_headers(secrets))
    if status not in (200, 201):
        raise SystemExit('embedding request failed: HTTP %s %s' % (status, body[:300]))
    vectors = [item['embedding'] for item in json.loads(body)['data']]
    for v in vectors:
        if len(v) != EXPECTED_DIM:
            raise SystemExit('model returned %d dimensions, the table stores %d' % (len(v), EXPECTED_DIM))
    return vectors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*', help='markdown files (default: every *.md in --dir)')
    ap.add_argument('--dir', default='knowledge')
    ap.add_argument('--secrets', default=DEFAULT_SECRETS)
    ap.add_argument('--replace', action='store_true', help='delete existing chunks of these files first')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    files = args.files or sorted(glob.glob(os.path.join(args.dir, '*.md')))
    if not files:
        sys.exit('no markdown files found')

    plan = [(f, chunk_file(f)) for f in files]
    for f, chunks in plan:
        print('%-28s %2d chunks  %5d chars' % (os.path.basename(f), len(chunks),
                                               sum(len(c['content']) for c in chunks)))
    if args.dry_run:
        print('dry run: nothing was sent')
        return 0

    secrets = read_secrets(args.secrets)
    table = secrets['supabaseUrl'] + '/rest/v1/documents'

    for path, chunks in plan:
        name = os.path.basename(path)
        vectors = embed([c['content'] for c in chunks], secrets)
        rows = [{
            'content': c['content'],
            'embedding': v,
            'metadata': {'source': name, 'loc': {'lines': {'from': c['from'], 'to': c['to']}},
                         'blobType': 'text/markdown'},
        } for c, v in zip(chunks, vectors)]

        if args.replace:
            status = delete(table + '?metadata->>source=eq.' + urllib.parse.quote(name), secrets)
            print('%-28s deleted old rows (HTTP %s)' % (name, status))
        status, body = post(table, rows, _supabase_headers(secrets))
        if status not in (200, 201, 204):
            raise SystemExit('%s: insert failed HTTP %s %s' % (name, status, body[:300]))
        print('%-28s %2d chunks stored with source=%s (HTTP %s)' % (name, len(rows), name, status))
    return 0


if __name__ == '__main__':
    import urllib.parse  # noqa: E402  (used in main for the delete filter)
    sys.exit(main())
