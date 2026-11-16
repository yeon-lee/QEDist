from pathlib import Path
from collections import defaultdict


def main():
    for s in 'XZ':
        lines=Path(s+'.sym').read_text().splitlines()
        n,m,o,g=map(int,lines[0].split()[1:])
        cols=[0]*n
        for i,ln in enumerate(lines[1:]):
            for j in map(int,ln.split()[1:]): cols[j]|=1<<i
        single={v:j for j,v in enumerate(cols)}
        triples=set()
        groups={}
        quads=set()
        for j,col in enumerate(cols):
            for k in range(j):
                v=col^cols[k]
                if v in single: triples.add(tuple(sorted((j,k,single[v]))))
                if v in groups:
                    a,b=groups[v]
                    quads.add(tuple(sorted((a,b,j,k))))
                else: groups[v]=(j,k)
        neutral=sorted(triples)+sorted(quads)
        for row in neutral:
            sig=0
            for i in row: sig^=cols[i]
            assert sig==0 and len(set(row))==len(row)
        print(s,len(triples),len(quads))
        with open(s+'.relations','w') as f:
            print('QEDIST_CIRCUIT_V1',n,m,o,len(neutral),file=f)
            for ln in lines[1:]: print(ln,file=f)
            for row in neutral: print(len(row),*row,file=f)


if __name__ == "__main__":
    main()
