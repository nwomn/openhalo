"""Fetch one pinned gated checkpoint using the owner's existing Jetson login."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import requests

MODEL = 'embedl/Qwen3.5-0.8B-FlashHead'
REVISION = '6208c90544971d154eefc047e6f84d05326fa031'
ROOT = Path('/home/jetson/openhalo-qwen35-flashhead')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default=MODEL)
    parser.add_argument('--revision',default=REVISION)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    dest=args.root/'assets/model'
    dest.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    token=(Path.home()/'.cache/huggingface/token').read_text().strip()
    session.headers['Authorization']='Bearer '+token
    response=session.get(f'https://huggingface.co/api/models/{args.model}/revision/{args.revision}',params={'blobs':'true'},timeout=30)
    response.raise_for_status()
    info=response.json()
    records=[]
    for entry in info['siblings']:
        name=entry['rfilename']
        path=dest/name
        assert path.resolve().is_relative_to(dest.resolve())
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists() or path.stat().st_size!=entry['size']:
            r=session.get(f'https://huggingface.co/{args.model}/resolve/{args.revision}/{name}',stream=True,timeout=(30,120))
            r.raise_for_status()
            temporary=path.with_name(path.name+'.partial')
            with temporary.open('wb') as handle:
                count=0
                for chunk in r.iter_content(8*1024*1024):
                    handle.write(chunk)
                    count+=len(chunk)
                    if count%(128*1024*1024)==0:
                        print(json.dumps(dict(file=name,downloaded_bytes=count)),flush=True)
            os.replace(temporary,path)
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(8*1024*1024),b''):
                digest.update(chunk)
        expected=(entry.get('lfs') or {}).get('sha256')
        assert path.stat().st_size==entry['size']
        assert not expected or digest.hexdigest()==expected
        records.append(dict(path=name,bytes=path.stat().st_size,sha256=digest.hexdigest(),upstream_lfs_sha256=expected))
        print(json.dumps(records[-1]),flush=True)
    (args.root/'assets/manifest.json').write_text(json.dumps(dict(model=args.model,revision=args.revision,files=records),indent=2))


if __name__=='__main__':
    main()
