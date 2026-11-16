    int even_repair_cap=0;
    uint64_t even_calls=0,even_attempts=0,even_successes=0,even_prunes=0;
    std::ofstream even_proofs;uint64_t even_proofs_written=0;
    int even_load(int v)const{return fractional_mark[v]==fractional_epoch?fractional_load[v]:0;}
    void even_add(int v,int delta){
        if(fractional_mark[v]!=fractional_epoch){fractional_mark[v]=fractional_epoch;fractional_load[v]=0;}
        fractional_load[v]=int(fractional_load[v])+delta;
    }
    void even_certificate(int wt,int budget,int count,const int*ids,int D,int nb,const int*bq,const int*bv){
        if(!even_proofs.is_open()||even_proofs_written>=64)return;++even_proofs_written;
        even_proofs<<"{\"node\":"<<nodes<<",\"wt\":"<<wt<<",\"K\":"<<effective_W<<",\"budget\":"<<budget<<",\"sw\":"<<sw<<",\"S\":[";
        bool comma=false;for(int v=0;v<c.n;++v)if(bit(selected,v)){if(comma)even_proofs<<',';even_proofs<<v;comma=true;}
        even_proofs<<"],\"unavailable\":[";comma=false;for(int v=0;v<c.n;++v)if(forbidden[v]){if(comma)even_proofs<<',';even_proofs<<v;comma=true;}
        even_proofs<<"],\"odd_rows\":[";for(int i=0;i<count;++i){if(i)even_proofs<<',';even_proofs<<ids[i];}
        even_proofs<<"],\"available_rows\":[";
        for(int i=0;i<count;++i){if(i)even_proofs<<',';even_proofs<<'[';bool comma=false;uint64_t a=available[ids[i]];
            while(a){int b=__builtin_ctzll(a);a&=a-1;if(comma)even_proofs<<',';even_proofs<<c.hr[ids[i]][b];comma=true;}even_proofs<<']';}
        even_proofs<<"],\"certificate\":{\"denominator\":"<<D<<",\"odd_terms\":[";
        for(int i=0;i<count;++i){if(i)even_proofs<<',';even_proofs<<'['<<ids[i]<<','<<fractional_weights[ids[i]]<<']';}
        even_proofs<<"],\"even_terms\":[";for(int i=0;i<nb;++i){if(i)even_proofs<<',';even_proofs<<'['<<bq[i]<<','<<bv[i]<<",1]";}even_proofs<<"]}}\n";
    }
    bool even_bound(int wt,int budget,int count,const int*ids,const int*next,const int*head,int minavail,int D,int &total){
        ++even_calls;int attempts=0,nb=0,bq[128],bv[128];
        for(int degree=minavail;degree<=maxrow;++degree)for(int k=head[degree];k>=0;k=next[k]){
            if(attempts>=16)return false;
            // Every remaining attempt can increase the objective by at most one.
            if(total+std::min(16-attempts,count-attempts)<=D*budget)return false;
            ++attempts;++even_attempts;
            int row=ids[k],changed_v[576],changed_delta[576],nc=0,over[64],no=0,trial_q[8],trial_v[8],nt=0;
            auto change=[&](int v,int delta){even_add(v,delta);changed_v[nc]=v;changed_delta[nc++]=delta;};
            uint64_t a=available[row];while(a){int b=__builtin_ctzll(a);a&=a-1;int v=c.hr[row][b];change(v,1);if(even_load(v)>D)over[no++]=v;}
            bool ok=no<=even_repair_cap;
            for(int i=0;i<no&&ok;++i){int v=over[i],repair=-1;
                for(int q:c.vc[v])if(!unsatisfied(q)){
                    bool fits=true;uint64_t a=available[q];while(a){int b=__builtin_ctzll(a);a&=a-1;int u=c.hr[q][b];if(u!=v&&even_load(u)>=D){fits=false;break;}}
                    if(fits){repair=q;break;}
                }
                if(repair<0){ok=false;break;}
                trial_q[nt]=repair;trial_v[nt++]=v;
                uint64_t a=available[repair];while(a){int b=__builtin_ctzll(a);a&=a-1;int u=c.hr[repair][b];change(u,u==v?-1:1);}
            }
            if(!ok){while(nc){--nc;even_add(changed_v[nc],-changed_delta[nc]);}continue;}
            ++even_successes;++total;if(even_proofs.is_open())++fractional_weights[row];
            for(int i=0;i<nt;++i){bq[nb]=trial_q[i];bv[nb++]=trial_v[i];}
            // Weighted odd and even inequalities give total <= sum_v load(v)x_v.
            // Every load remains <= D; hence total > D*budget excludes a completion.
            if(total>D*budget){++even_prunes;even_certificate(wt,budget,count,ids,D,nb,bq,bv);return true;}
        }
        return false;
    }
