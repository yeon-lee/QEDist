import sys

if sys.version_info < (3, 10):
    print('cssdist requires Python 3.10 or newer; use python3.12 or another supported interpreter.', file=sys.stderr)
    raise SystemExit(2)

from .cli import main

raise SystemExit(main())
