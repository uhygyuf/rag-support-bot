#!/usr/bin/env python3
"""Live check of the Supabase knowledge base (needs credentials, reads only).

The static suite cannot see the live store, which is where both answering defects of
2026-09-22 lived: every chunk carried `metadata.source = "blob"` (so citations were
meaningless) and `knowledge/policies.md` had never been loaded at all. This check closes
that gap: it reads `documents` and compares it against the repository's own documents.

    python tests/kb_live_check.py                    # uses the default secrets file
    python tests/kb_live_check.py --secrets <path>

Secrets file: {"supabaseUrl": ..., "serviceKey": ...} (+ the embedding fields, unused here).
When the file is absent the check reports SKIP with the command that enables it, and exits 0,
so it never blocks a machine without credentials.

Exit code 0 = every assertion held (or the check was skipped), 1 = a real failure.
"""

import argparse
import importlib.util
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_SECRETS = os.environ.get('INGEST_SECRETS', r'D:\Tools\n8n\demo-secrets.json')
USER_AGENT = 'rag-support-bot-kb-check/1.0'
RESULTS = []


def load_ingest():
    spec = importlib.util.spec_from_file_location('ingest', os.path.join(ROOT, 'tools', 'ingest.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(cid, desc, ok, detail=''):
    RESULTS.append({'id': cid, 'description': desc, 'status': 'PASS' if ok else 'FAIL',
                    'detail': str(detail)[:300]})
    print('  %-4s %-6s %s%s' % ('PASS' if ok else 'FAIL', cid, desc,
                                ('  [' + str(detail)[:110] + ']') if detail else ''))


def fetch_rows(secrets):
    url = secrets['supabaseUrl'].rstrip('/') + '/rest/v1/documents?select=id,metadata&order=id'
    req = urllib.request.Request(url, headers={
        'apikey': secrets['serviceKey'],
        'Authorization': 'Bearer ' + secrets['serviceKey'],
        'User-Agent': USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--secrets', default=DEFAULT_SECRETS)
    ap.add_argument('--dir', default=os.path.join(ROOT, 'knowledge'))
    args = ap.parse_args()

    print('LIVE KNOWLEDGE BASE CHECK')
    print('=' * 78)
    if not os.path.exists(args.secrets):
        print('  SKIP   no secrets file at %s' % args.secrets)
        print('         enable it with: python tests/kb_live_check.py --secrets <path>')
        print('         (the file needs supabaseUrl + serviceKey; see docs/operations.md 3.4)')
        print('RESULT: SKIPPED (not covered by this run)')
        return 0

    with open(args.secrets, encoding='utf-8') as fh:
        secrets = json.load(fh)
    ingest = load_ingest()
    rows = fetch_rows(secrets)

    expected_files = sorted(f for f in os.listdir(args.dir) if f.endswith('.md'))
    plan = {f: len(ingest.chunk_file(os.path.join(args.dir, f))) for f in expected_files}
    sources = {}
    for row in rows:
        src = (row.get('metadata') or {}).get('source')
        sources.setdefault(src, []).append(row['id'])

    check('K1', 'the knowledge base is not empty', bool(rows), '%d rows' % len(rows))
    check('K2', 'every chunk names a source file, none says "blob" or is empty',
          all(isinstance(s, str) and s and s != 'blob' for s in sources),
          'sources=%s' % sorted(str(s) for s in sources))
    check('K3', 'every repository document is loaded',
          all(f in sources for f in expected_files),
          'missing=%s' % [f for f in expected_files if f not in sources])
    check('K4', 'no stored chunk comes from a file that is not in knowledge/',
          all(s in expected_files for s in sources),
          'unexpected=%s' % [s for s in sources if s not in expected_files])
    check('K5', 'the chunk count per file matches what tools/ingest.py would write',
          all(len(sources.get(f, [])) == plan[f] for f in expected_files),
          'stored=%s plan=%s' % ({f: len(sources.get(f, [])) for f in expected_files}, plan))

    failed = [r for r in RESULTS if r['status'] == 'FAIL']
    with open(os.path.join(HERE, 'kb-results.json'), 'w', encoding='utf-8') as fh:
        json.dump({'rows': len(rows),
                   'sources': {str(k): len(v) for k, v in sources.items()},
                   'expected': plan, 'results': RESULTS}, fh, indent=1)
    print('-' * 78)
    print('LIVE KB: %d cases, %d failed' % (len(RESULTS), len(failed)))
    print('RESULT: %s' % ('ALL PASS' if not failed else '%d FAILURE(S)' % len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
