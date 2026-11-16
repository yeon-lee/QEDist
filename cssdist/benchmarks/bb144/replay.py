"""Replay measured witnesses through IBM's gates and both noiseless readout rounds."""
import contextlib, io, json, runpy
from pathlib import Path
import numpy as np


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        src=runpy.run_path('decoder_setup.py')
    out={}
    for path in sorted(Path('.').glob('*-10.jsonl')):
        lines=[json.loads(l) for l in path.read_text().splitlines()]
        if not lines or lines[0]['event']!='witness': continue
        sector,mode,_=path.name.split('-')
        support=lines[0]['support']
        if mode!='model':
            order=json.loads(Path(sector+'.sym.json').read_text())['orig_index']
            support=[order[i] for i in support]
        groups=[v for sig,v in src['H'+sector+'dict'].items() if sig]
        cycle=src['cycle']
        inserted={}; locations=[]
        for i in support:
            c=src['circuits'+sector][groups[i][0]]
            pos=next(j for j,g in enumerate(c) if g[0] in (sector,sector*2))
            op=c[pos]
            # Upstream inserts errors immediately before measurement or after other gates.
            inserted.setdefault(pos,[]).append(op)
            # Identify physical source using the generator's original fault enumeration order.
            locations.append(groups[i][0])
        guide=[]
        for j,g in enumerate(cycle):
            if g[0]=='CNOT': guide.extend([j]*3)
            if g[0] in ('IDLE','Meas'+('X' if sector=='Z' else 'Z'),'Prep'+('X' if sector=='Z' else 'Z')): guide.append(j)
        gates=[guide[i] for i in locations]
        assert len(set(gates))==len(support)
        circuit=[]
        for pos in range(len(cycle)+1):
            circuit.extend(inserted.get(pos,[]))
            if pos<len(cycle): circuit.append(cycle[pos])
        sy,state,_,count=src['simulate_circuit'+sector](circuit+cycle+cycle)
        assert count==len(support) and not np.any(sy)
        L=src['lz' if sector=='X' else 'lx']
        bits=np.flatnonzero(np.asarray(L@[state[src['lin_order'][q]] for q in src['data_qubits']]).reshape(-1)%2).tolist()
        assert bits
        out[path.name]=dict(weight=count,gate_indices=gates,logical_bits=bits,raw_measurement_flips=0)
    Path('replayed.json').write_text(json.dumps(out,indent=2)+'\n')
    print(out)


if __name__ == "__main__":
    main()
