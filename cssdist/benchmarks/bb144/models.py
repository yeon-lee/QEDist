import pickle
from pathlib import Path
import numpy as np


def main():
    base = Path(__file__).resolve().parent
    with (base / 'TMP/mydata_144_12_p_0.003_cycles_1').open('rb') as f:
        data = pickle.load(f)
    for sector in "XZ":
        H = data['H'+sector].tocsc()
        m = data['first_logical_row'+sector]
        assert H.shape[0]-m==12 and m==216
        cols = [i for i in range(H.shape[1]) if H.indptr[i] < H.indptr[i+1]]
        rows = H[:,cols].tocsr()
        with (base / (sector+'.model')).open('w') as f:
            print('QEDIST_CIRCUIT_V1',len(cols),m,12,0,file=f)
            for row in rows:
                ids = sorted(row.indices)
                print(len(ids),*ids,file=f)
        print(sector,len(cols))


if __name__ == "__main__":
    main()
