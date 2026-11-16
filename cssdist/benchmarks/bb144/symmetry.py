"""Verify independent translations on detectors and the joint silent-fault kernel."""
from pathlib import Path
import hashlib, json


def main():
    base = Path(__file__).resolve().parent

    def insert(basis, x, extend):
        while x:
            i = x.bit_length()-1
            if i not in basis:
                if extend: basis[i] = x
                return False
            x ^= basis[i]
        return True

    for s in "XZ":
        lines = (base/(s+".model")).read_text().splitlines()
        _,n,m,k,g=lines[0].split()
        n,m,k=map(int,(n,m,k))
        rows = [list(map(int,l.split()[1:])) for l in lines[1:]]
        cols=[[] for _ in range(n)]
        for i,row in enumerate(rows[:m]):
            for j in row: cols[j].append(i)
        idx={tuple(v):j for j,v in enumerate(cols)}
        assert len(idx)==n
        joint={}
        for row in rows: insert(joint,sum(1<<j for j in row),True)
        def shift(i, dx, dy):
            t,site=divmod(i,72)
            x,y=divmod(site,6)
            return 72*t + 6*((x+dx)%12) + ((y+dy)%6)
        perms=[]
        for dx,dy in ((1,0),(0,1)):
            p=[idx[tuple(sorted(shift(i,dx,dy) for i in col))] for col in cols]
            assert sorted(p)==list(range(n))
            # D transforms by a row permutation. Invariance of row(D,O)
            # additionally ensures preservation of zero/nonzero logical action.
            assert all(insert(joint,sum(1<<p[j] for j in row),False) for row in rows[m:])
            perms.append(p)
        unseen=set(range(n)); reps=[]; sizes=[]
        while unseen:
            rep=min(unseen); stack=[rep]; unseen.remove(rep); size=0
            while stack:
                i=stack.pop(); size+=1
                for p in perms:
                    if p[i] in unseen:
                        unseen.remove(p[i]); stack.append(p[i])
            reps.append(rep); sizes.append(size)
        order=reps+[i for i in range(n) if i not in set(reps)]
        orderidx={v:i for i,v in enumerate(order)}
        with (base/(s+'.sym')).open('w') as f:
            print(lines[0],file=f)
            for row in rows: print(len(row),*sorted(orderidx[i] for i in row),file=f)
        (base/(s+'.sym.json')).write_text(json.dumps(dict(roots=len(reps),orbit_sizes=sizes,orig_index=order,detector_translation_verified=True,joint_rowspace_verified=True)))
        print(s,len(reps),sizes)


if __name__ == "__main__":
    main()
