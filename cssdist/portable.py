"""Portable execution evidence with read-only auditing and no binary execution."""
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

from . import __version__
from .audit import audit_run, require, require_object
from .calibration import audit_calibration
from .code import digest, json_bytes

SCHEMA = 'cssdist.portable.v1'
MAX_BYTES = 2 * 1024**3
MAX_FILES = 100000
AUDIT_COMMANDS = {'certification': 'audit', 'calibration': 'audit-calibration',
                  'circuit': 'audit-circuit', 'stabilizer': 'audit-stabilizer'}


def _audit(root, kind):
    if kind == 'certification':
        return audit_run(root)
    if kind == 'circuit':
        from .circuit_run import audit_circuit
        return audit_circuit(root)
    if kind == 'stabilizer':
        from .stabilizer_run import audit_stabilizer
        return audit_stabilizer(root)
    require(kind == 'calibration', 'Unknown evidence kind')
    return audit_calibration(root)


def _files(root):
    result = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Evidence contains a symbolic link')
        if path.is_file():
            require(path.resolve().is_relative_to(root.resolve()), 'Evidence path escapes root')
            result.append(path)
        else:
            require(path.is_dir(), 'Evidence contains a nonregular file')
    return result


def export_bundle(directory, output):
    """Snapshot, audit, and export an inactive campaign; never modify its records."""
    root = Path(directory).resolve()
    output = Path(output).absolute()
    require(root.is_dir(), 'Evidence directory does not exist')
    require(not output.exists(), 'Bundle output already exists')
    require(not output.resolve().is_relative_to(root), 'Bundle output must be outside evidence directory')
    require(not (root/'.running.lock').exists(), 'Cannot export an active or locked campaign')
    kinds = [kind for kind, name in [('certification','campaign.json'),('calibration','calibration.json'),
                                      ('circuit','config.json'),('stabilizer','stabilizer_run.json')]
             if (root/name).is_file()]
    require(len(kinds) == 1, 'Expected exactly one CSS, stabilizer, circuit, or calibration run')
    kind = kinds[0]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.cssdist-export-', dir=output.parent) as tmp:
        stage = Path(tmp)/'snapshot'; evidence = stage/'evidence'; evidence.mkdir(parents=True)
        files = _files(root)
        require(len(files) <= MAX_FILES and sum(p.stat().st_size for p in files) <= MAX_BYTES,
                'Evidence exceeds portable bundle limits')
        for p in files:
            q = evidence/p.relative_to(root); q.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,q)
        result = _audit(evidence, kind)
        package = Path(__file__).resolve().parent
        # Preserve the checker source for review/replay, not automatic execution.
        for p in _files(package):
            if '__pycache__' in p.parts or p.suffix not in ('.py','.cpp','.hpp','.inc','.json','.txt'):
                continue
            q = stage/'checker/cssdist'/p.relative_to(package)
            q.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,q)
        instruction = ('This archive contains execution evidence, not a formal proof trace.\n'
            'Auditing does not run the archived native executable.\n'
            'Activate a Python 3.10+ environment with QEDist installed.\n'
            'Using a trusted compatible package: python -m cssdist audit-bundle ARCHIVE\n'
            'After inspecting and extracting the archived checker source, optional replay:\n'
            f'PYTHONPATH=checker python -m cssdist {AUDIT_COMMANDS[kind]} evidence\n'
            'A fresh exhaustive run is separate and may be expensive.\n')
        (stage/'VERIFY.txt').write_text(instruction)
        members = _files(stage)
        manifest = {'schema':SCHEMA,'kind':kind,'package_version':__version__,
                    'files':{str(p.relative_to(stage)):digest(p.read_bytes()) for p in members},
                    'audited_result':result,'evidence_kind':'Trusted exhaustive execution records, not per-node proof objects.'}
        (stage/'MANIFEST.json').write_bytes(json_bytes(manifest))
        packed = Path(tmp)/'bundle.tar.gz'
        with packed.open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w') as archive:
                for p in _files(stage):
                    data=p.read_bytes(); info=tarfile.TarInfo(str(p.relative_to(stage)))
                    info.size=len(data);info.mode=0o644;info.mtime=0
                    archive.addfile(info,io.BytesIO(data))
        # Re-read the actual archive rather than trusting the staging result.
        checked = audit_bundle(packed)
        require(checked['result'] == result, 'Portable audit changed the result')
        # Both paths are on the same filesystem. Publish the complete archive at once.
        os.link(packed, output)
    return {'schema':SCHEMA,'archive':str(output),'sha256':digest(output.read_bytes()),
            'kind':kind,'result':result}


def audit_bundle(path):
    """Validate safe members and hashes, then recompute the distance interpretation.

    Archived executable and checker source are never executed by this command.
    The installed package must recognize the recorded native source profile.
    """
    with tempfile.TemporaryDirectory(prefix='cssdist-audit-bundle-') as tmp:
        root=Path(tmp); names=set(); total=0
        with tarfile.open(path,mode='r:gz') as archive:
            for item in archive:
                name=PurePosixPath(item.name)
                require(item.isfile() and item.name not in names and not name.is_absolute()
                        and all(x not in ('..','.') for x in name.parts)
                        and str(name)==item.name and '\\' not in item.name,
                        'Unsafe, duplicate, or nonregular archive member')
                require(name.parts and name.parts[0] in ('evidence','checker','MANIFEST.json','VERIFY.txt'),
                        'Unknown archive member')
                require(item.size >= 0, 'Negative archive member size')
                names.add(item.name);total+=item.size
                require(len(names) <= MAX_FILES and total <= MAX_BYTES, 'Archive exceeds portable bundle limits')
                target=root/item.name;target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(item) as source, target.open('xb') as dest:
                    shutil.copyfileobj(source,dest)
        manifest=require_object(json.loads((root/'MANIFEST.json').read_text()), 'Portable manifest')
        require(manifest.get('schema')==SCHEMA and type(manifest.get('files')) is dict,'Unknown portable schema')
        require(set(manifest['files']) == names-{'MANIFEST.json'}, 'Archive manifest membership mismatch')
        for name, expected in manifest['files'].items():
            require(digest((root/name).read_bytes())==expected, 'Archive checksum mismatch: '+name)
        result=_audit(root/'evidence',manifest['kind'])
        require(result==manifest['audited_result'],'Stored bundle result differs from fresh audit')
        return {'schema':SCHEMA,'status':'PASS','kind':manifest['kind'],
                'archive_sha256':digest(Path(path).read_bytes()),'result':result,
                'executed_archived_code':False}
