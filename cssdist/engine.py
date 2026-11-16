"""Compile the CSS and lifted-product search engines and check input limits."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .code import digest, json_bytes

NATIVE = Path(__file__).resolve().parent / 'native_css'
NATIVE_INTEGER_MAX = 2**31 - 1
LIMITS = dict.fromkeys(('n', 'check_rows', 'stabilizer_rows', 'check_row_weight', 'cutoff'),
                       NATIVE_INTEGER_MAX)
_FIXED_LIMITS = {'n': 8192, 'check_rows': 2048, 'stabilizer_rows': 2048,
                 'check_row_weight': 64, 'cutoff': 64}
DEFAULT_PROFILE = 'css'
PROFILES = {'css': NATIVE, 'lp': NATIVE.parent / 'native_lp'}
# These names identify the same retained sources in existing execution records.
_PROFILE_ALIASES = {'weighted8192': 'css', 'lpblocks8192': 'lp'}
FLAGS = ['-O3', '-std=c++17']
# Recognize the first 0.1 cyclic-only execution records without distributing
# their engines. Their command, coverage and transcript checks are unchanged.
_CYCLIC_01_SOURCES = {
    'common.hpp': 'd89eb574db637fcc428b491dccd44f4ba2061ca578b3ea077f73e53311b606ca',
    'even_methods.inc': '2b38d728b2af897ff06e336b8926daab0ff90c6ecc8f48bd2e4cdda9da1c78e0',
}
_CYCLIC_01_EXACT = {
    'css': 'fb732b0dc9ab96cdcff087886678bf96ce275854f8f03562e7c31f39883771cd',
    'lp': 'b26c2b4fb1544998d9200cfd76053d57df6349f52d6fb51fc2da14da501a2765',
}
_PRE_ADDITION_SOURCES = {
    'common.hpp': 'd89eb574db637fcc428b491dccd44f4ba2061ca578b3ea077f73e53311b606ca',
    'even_methods.inc': '2b38d728b2af897ff06e336b8926daab0ff90c6ecc8f48bd2e4cdda9da1c78e0',
    'symmetry.hpp': '6077b730861a2a751cc35b66449c8d34adb67715d249321bf61384140f635f65',
}
_PRE_ADDITION_EXACT = {
    'css': 'a89e0b8652a5a1dae91d40dc1df317f1067460a0302cfe2f26dff38083cbf563',
    'lp': '2e2fe9392f010cc0c4fce1a4715b3632a2edd390e4512d4e773ee5c315aea38d',
}
_FIXED_STORAGE_SOURCES = {
    'common.hpp': 'd89eb574db637fcc428b491dccd44f4ba2061ca578b3ea077f73e53311b606ca',
    'even_methods.inc': '8b9afa080de612320d3837e90524b176e0a3e828197f39be8363c82c320dac07',
    'symmetry.hpp': '6077b730861a2a751cc35b66449c8d34adb67715d249321bf61384140f635f65',
}
_FIXED_STORAGE_EXACT = {
    'css': 'd4831f956884f1839accfccd000aee398fc823c4c94345479dcfa821d8b9451b',
    'lp': '8f084f7427617fddd3516ee2326dcabd97c8cd1132787b826d7e036759ca0e04',
}


def uses_dynamic_storage(sources):
    """Call only after checking the complete source identity."""
    return sources['common.hpp'] != _FIXED_STORAGE_SOURCES['common.hpp']


def memory_budget_bytes(memory_mib):
    if memory_mib is None:
        return None
    if (type(memory_mib) not in (int, float) or not 0 < memory_mib < 2**44
            or not math.isfinite(memory_mib)):
        raise ValueError('memory_mib must be a finite positive number below 2**44')
    return math.ceil(memory_mib * 1024**2)


def validate_memory_bytes(value):
    if value is not None and (type(value) is not int or not 1 <= value < 2**64):
        raise ValueError('Invalid native memory budget')
    return value


def source_hashes(directory=NATIVE, *, expected_names=None, context='Native source'):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Native source directory is a symbolic link')
    files = sorted(p for p in directory.iterdir() if p.suffix in ('.cpp', '.hpp', '.inc'))
    names = {p.name for p in files}
    if (not {'exact.cpp', 'common.hpp'} <= names or
            (expected_names is not None and names != set(expected_names))):
        raise ValueError(f'{context}: file inventory differs from its profile')
    if any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('Native source must be a regular file')
    return {p.name: digest(p.read_bytes()) for p in files}


def canonical_profile(profile):
    if type(profile) is not str:
        raise ValueError(f'Unknown native profile: {profile}')
    name = _PROFILE_ALIASES.get(profile, profile)
    if name not in PROFILES:
        raise ValueError(f'Unknown native profile: {profile}')
    return name


def audited_source_hashes(directory, profile, *, allow_cyclic_01=True,
                          proposed_additions=False):
    profile = canonical_profile(profile)
    if type(proposed_additions) is not bool:
        raise ValueError('proposed_additions must be a boolean')
    actual = source_hashes(directory)
    accepted = [source_hashes(profile_directory(profile)),
                dict(_FIXED_STORAGE_SOURCES, **{'exact.cpp': _FIXED_STORAGE_EXACT[profile]})]
    if not proposed_additions:
        accepted.append({**_PRE_ADDITION_SOURCES, 'exact.cpp': _PRE_ADDITION_EXACT[profile]})
    if allow_cyclic_01 and not proposed_additions:
        accepted.append(dict(_CYCLIC_01_SOURCES, **{'exact.cpp': _CYCLIC_01_EXACT[profile]}))
    if all(set(actual) != set(candidate) for candidate in accepted):
        raise ValueError('Native source file inventory differs from its profile')
    if actual not in accepted:
        raise ValueError('Search source differs from a recognized package engine')
    return actual


def profile_directory(profile=DEFAULT_PROFILE, *, large_capacity=True):
    if type(large_capacity) is not bool:
        raise ValueError('large_capacity must be a boolean')
    directory = PROFILES[canonical_profile(profile)]
    return directory if large_capacity else directory / 'fixed'


def select_capacity(required, requested=None, memory_bytes=None):
    """Use the compact engine when it can honor all requested resources."""
    if requested is not None and type(requested) is not bool:
        raise ValueError('large_capacity must be a boolean or None')
    if requested is False and (required or memory_bytes is not None):
        raise ValueError('The input, cutoff or memory budget requires --large-capacity; '
                         'omit --no-large-capacity to select it automatically')
    if requested is not None:
        return requested
    return required or memory_bytes is not None


def select_code_capacity(code, cutoff, requested=None, memory_bytes=None):
    check_limits(code, cutoff)
    required = (code.n > _FIXED_LIMITS['n'] or cutoff > _FIXED_LIMITS['cutoff']
                or any(len(rows) > _FIXED_LIMITS['check_rows']
                       or any(row.bit_count() > _FIXED_LIMITS['check_row_weight'] for row in rows)
                       for rows in (code.hx, code.hz)))
    return select_capacity(required, requested, memory_bytes)


def profile_options(profile, proposed_additions=False):
    """Both engines use the same recorded pruning and check-selection policy."""
    # Callers resolve the public default or saved setting. An omitted native
    # flag keeps its original disabled meaning when auditing old commands.
    canonical_profile(profile)
    if type(proposed_additions) is not bool:
        raise ValueError('proposed_additions must be a boolean')
    options = ['fractional=2', 'repair-depth=8', 'even-repairs=4']
    if proposed_additions:
        options.append('proposed-additions=on')
    return options


def profile_limits(profile=DEFAULT_PROFILE):
    profile_directory(profile)
    return dict(LIMITS)


def check_limits(code, cutoff, profile=DEFAULT_PROFILE, *, legacy=False):
    limits = _FIXED_LIMITS if legacy else profile_limits(profile)
    if code.k == 0:
        raise ValueError('This code has k=0; nontrivial logical distance is undefined')
    if type(cutoff) is not int or not 1 <= cutoff <= limits['cutoff']:
        raise ValueError(f'The current backend requires 1 <= cutoff <= {limits["cutoff"]}')
    if code.n > limits['n']:
        raise ValueError(f'The {profile} backend supports at most {limits["n"]} qubits')
    for label, rows in [('X', code.hx), ('Z', code.hz)]:
        if len(rows) > limits['check_rows']:
            raise ValueError(f'The backend supports at most {limits["check_rows"]} {label} check rows')
        if any(row.bit_count() > limits['check_row_weight'] for row in rows):
            raise ValueError(f'The backend supports check rows of weight at most {limits["check_row_weight"]}')


def compiler_identity(compiler):
    path = shutil.which(compiler)
    if path is None:
        raise ValueError(f'C++17 compiler not found: {compiler}')
    result = subprocess.run([path, '--version'], capture_output=True, text=True, check=True)
    return str(Path(path).resolve()), result.stdout.strip()


def build(destination, compiler='c++', cache=None, profile=DEFAULT_PROFILE, *, large_capacity=True):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    compiler_path, version = compiler_identity(compiler)
    native = profile_directory(profile, large_capacity=large_capacity)
    sources = source_hashes(native)
    identity = {'source_sha256': sources, 'compiler': compiler_path,
                'compiler_version': version, 'flags': FLAGS}
    cache = Path(cache) if cache else Path(tempfile.gettempdir()) / f'cssdist-native-{os.getuid()}'
    cache.mkdir(parents=True, exist_ok=True)
    key = digest(json_bytes(identity))
    entry = cache / key
    valid = False
    try:
        if (entry / 'build.json').is_file() and (entry / 'exact').is_file():
            saved = json.loads((entry / 'build.json').read_text())
            valid = (saved.get('identity') == identity
                     and saved.get('executable_sha256') == digest((entry / 'exact').read_bytes()))
    except (OSError, ValueError, AttributeError):
        # An interrupted writer or corrupt cache is not campaign evidence.
        valid = False
    if not valid:
        with tempfile.TemporaryDirectory(prefix='build-', dir=cache) as tmp:
            out = Path(tmp) / 'exact'
            for name in sources:
                shutil.copy2(native / name, Path(tmp) / name)
            if source_hashes(tmp) != sources:
                raise ValueError('Native source changed during build preparation')
            subprocess.run([compiler_path, *FLAGS, str(Path(tmp) / 'exact.cpp'), '-o', str(out)],
                           capture_output=True, text=True, check=True)
            saved = {'identity': identity, 'executable_sha256': digest(out.read_bytes())}
            entry.mkdir(exist_ok=True)
            # Files become visible whole. Concurrent builds of the same identity
            # cannot expose a partially copied executable or partial JSON.
            metadata = Path(tmp) / 'build.json'
            metadata.write_bytes(json_bytes(saved))
            out.replace(entry / 'exact')
            metadata.replace(entry / 'build.json')
    for name in sources:
        shutil.copy2(native / name, destination / name)
    shutil.copy2(native / 'provenance.json', destination / 'provenance.json')
    shutil.copy2(Path(__file__).with_name('LICENSE.txt'), destination / 'LICENSE.txt')
    shutil.copy2(entry / 'exact', destination / 'exact')
    if source_hashes(destination) != sources or digest((destination / 'exact').read_bytes()) != saved['executable_sha256']:
        raise ValueError('Native source or cached executable changed during copy')
    (destination / 'build.json').write_bytes(json_bytes(saved))
    return saved
