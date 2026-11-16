// Exhaustive irreducible-support search. See README.txt for the proof of
// completeness, the coset-leader pruning rule, and the shard partition.
#include "common.hpp"
#include "symmetry.hpp"

// Every word in ker(H) has even Hamming weight exactly when the all-ones
// functional is a sum of check rows. Track that sum so a separate checker
// can validate the positive claim using XOR alone.
struct KernelParity {
    bool even=false;
    std::vector<int> certificate_rows;
    explicit KernelParity(const BinaryCode &c) {
        std::vector<Word> rows, combinations;
        std::vector<int> pivots;
        const int coefficient_words=(c.m+63)/64;
        for(int i=0;i<c.m;++i){
            Word row=c.H[i], combination{};toggle(combination,i);
            for(size_t j=0;j<rows.size();++j)if(bit(row,pivots[j])){
                xorin(row,rows[j],c.words);
                xorin(combination,combinations[j],coefficient_words);
            }
            for(int p=0;p<c.n;++p)if(bit(row,p)){
                rows.push_back(row);combinations.push_back(combination);pivots.push_back(p);break;
            }
        }
        Word ones{}, combination{};
        for(int j=0;j<c.n;++j)toggle(ones,j);
        for(size_t j=0;j<rows.size();++j)if(bit(ones,pivots[j])){
            xorin(ones,rows[j],c.words);
            xorin(combination,combinations[j],coefficient_words);
        }
        even=weight(ones,c.words)==0;
        if(even)for(int i=0;i<c.m;++i)if(bit(combination,i))certificate_rows.push_back(i);
    }
};


struct Exact {
    bool proposed_additions = false;
    uint64_t proposed_candidates = 0, proposed_prunes = 0, proposed_prefix_prunes = 0;
    int repair_depth=0;uint64_t repair_calls=0,repair_changes=0;
    int repair_check(int best,int wt,int degree,const int *ids,const int *next,const int *head){
        if(!repair_depth||wt>repair_depth||next[head[degree]]<0)return best;
        ++repair_calls;int winner=best,bestscore=-1;
        for(int k=head[degree];k>=0;k=next[k]){
            int j=ids[k],score=0;uint64_t a=available[j];
            while(a){int b=__builtin_ctzll(a);a&=a-1;for(int row:c.vc[c.hr[j][b]])score+=unsatisfied(row);}
            if(score>bestscore){winner=j;bestscore=score;}
        }
        repair_changes+=winner!=best;return winner;
    }

    BinaryCode c;KernelParity parity;int P,W,effective_W,root,begin,end,maxdeg=0,maxrow=0,sw=0,bad=0;bool use_parity=true;
    double seconds;uint64_t cap,nodes=0,coset_prunes=0,pack_prunes=0;
    bool found=false,incomplete=false,use_coset=true;Word selected{};
    std::string symmetry_file;
    bool hashed=false;int shard=0,shards=1,split_weight=1,roots_completed=0;
    uint64_t frontier_seen=0,frontier_owned=0,frontier_digest=0,common_nodes=0;
    std::vector<uint64_t> available,syndrome;
    std::vector<unsigned char> forbidden;
    std::vector<uint32_t> used_epoch;uint32_t packing_epoch=0;
    std::vector<int> overlap;
    std::vector<std::vector<std::pair<int,uint64_t>>> edges;
    std::array<int,MAXM> index;
    std::chrono::steady_clock::time_point start;
    int fractional_mode=0;uint64_t fractional_calls=0,fractional_prunes=0;
    std::vector<uint32_t> fractional_mark;uint32_t fractional_epoch=0;
    std::vector<uint16_t> fractional_load;
    std::ofstream fractional_proofs;uint64_t fractional_proof_limit=64,fractional_proofs_written=0;
    std::vector<int> fractional_weights;
#include "even_methods.inc"
    void fractional_certificate(int wt,int budget,int count,const int *ids,int denominator){
        if(!fractional_proofs.is_open()||fractional_proofs_written>=fractional_proof_limit)return;
        ++fractional_proofs_written;
        fractional_proofs<<"{\"node\":"<<nodes<<",\"wt\":"<<wt<<",\"K\":"<<effective_W<<",\"budget\":"<<budget<<",\"sw\":"<<sw<<",\"S\":[";
        bool comma=false;for(int v=0;v<c.n;++v)if(bit(selected,v)){if(comma)fractional_proofs<<',';fractional_proofs<<v;comma=true;}
        fractional_proofs<<"],\"unavailable\":[";comma=false;for(int v=0;v<c.n;++v)if(forbidden[v]){if(comma)fractional_proofs<<',';fractional_proofs<<v;comma=true;}
        fractional_proofs<<"],\"odd_rows\":[";
        for(int i=0;i<count;++i){if(i)fractional_proofs<<',';fractional_proofs<<ids[i];}
        fractional_proofs<<"],\"available_rows\":[";
        for(int i=0;i<count;++i){if(i)fractional_proofs<<',';fractional_proofs<<'[';uint64_t a=available[ids[i]];bool first=true;while(a){int b=__builtin_ctzll(a);a&=a-1;if(!first)fractional_proofs<<',';first=false;fractional_proofs<<c.hr[ids[i]][b];}fractional_proofs<<']';}
        fractional_proofs<<"],\"certificate\":{\"denominator\":"<<denominator<<",\"row_ids\":[";
        for(int i=0;i<count;++i){if(i)fractional_proofs<<',';fractional_proofs<<ids[i];}
        fractional_proofs<<"],\"weights\":[";for(int i=0;i<count;++i){if(i)fractional_proofs<<',';fractional_proofs<<fractional_weights[ids[i]];}fractional_proofs<<"]}}\n";
    }
    Exact(const std::string &path,int p,int w,double sec,int r,int b,int e,uint64_t cap,bool prune,bool parity_enabled):
      c(path),parity(c),P(p),W(w),effective_W(w-(parity_enabled&&parity.even&&(w%2))),root(r),begin(b),end(e),use_parity(parity_enabled),seconds(sec),cap(cap),use_coset(prune){
        if(W<1||W>64||root<0||root>=c.n/P||begin<0||end<=begin)throw std::runtime_error("invalid exact search parameters");
        c.validate_translation(P);edges.resize(c.n);available.resize(c.m);syndrome.resize((c.m+63)/64);forbidden.resize(c.n);overlap.resize(c.g);
        for(int j=0;j<c.m;++j){int d=c.hr[j].size();if(d>64)throw std::runtime_error("row degree exceeds 64");maxrow=std::max(maxrow,d);available[j]=d==64?~0ULL:((1ULL<<d)-1);
            for(int k=0;k<d;++k)edges[c.hr[j][k]].push_back({j,1ULL<<k});}
        used_epoch.resize(c.n);fractional_mark.resize(c.n);fractional_load.resize(c.n);fractional_weights.resize(c.m);
        for(auto &a:c.vc)maxdeg=std::max(maxdeg,int(a.size()));
    }
    bool unsatisfied(int j)const{return (syndrome[j/64]>>(j%64))&1;}
    void block(int v){forbidden[v]=1;for(auto [j,b]:edges[v])available[j]^=b;}
    void unblock(int v){forbidden[v]=0;for(auto [j,b]:edges[v])available[j]^=b;}
    void flip(int v,int delta){
        toggle(selected,v);for(int j:c.vc[v]){sw+=unsatisfied(j)?-1:1;syndrome[j/64]^=1ULL<<(j%64);}
        if(use_coset)for(int j:c.vg[v]){bad-=(2*overlap[j]>int(c.gr[j].size()));overlap[j]+=delta;bad+=(2*overlap[j]>int(c.gr[j].size()));}
    }
    bool independent(uint64_t a,int need,const uint64_t *adj,int &steps){
        if(need<=0)return true;if(__builtin_popcountll(a)<need||++steps>120)return false;
        int v=-1,mind=100;uint64_t tmp=a;
        while(tmp){int j=__builtin_ctzll(tmp);tmp&=tmp-1;int d=__builtin_popcountll(adj[j]&a);if(d<mind){v=j;mind=d;if(d<=1)break;}}
        // Adjacency includes the vertex itself: count <=2 means degree <=1.
        // Some maximum independent set contains an isolated or degree-one vertex.
        if(mind<=2)return independent(a&~adj[v],need-1,adj,steps);
        return independent(a&~adj[v],need-1,adj,steps)||independent(a&~(1ULL<<v),need,adj,steps);
    }
    static uint64_t mix(uint64_t x){
        x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
        x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);
    }
    void dfs(int wt,uint64_t key=0){
        ++nodes;
        if(nodes>cap||((nodes==1||(nodes&16383)==0)&&(stopped||elapsed(start)>=seconds))){incomplete=true;return;}
        // All shards traverse the same short prefix tree. At this frontier,
        // each subtree belongs to exactly one residue class; no pruning rule
        // depends on the shard. See README.txt for the coverage argument.
        if(hashed&&wt<=split_weight)++common_nodes;
        if(hashed&&wt==split_weight){
            ++frontier_seen;frontier_digest^=mix(key);if(key%uint64_t(shards)!=uint64_t(shard))return;++frontier_owned;
        }
        if(bad){++coset_prunes;return;}
        if(!sw){if(c.basis.nontrivial(selected)){
            if(!c.kernel(selected))throw std::runtime_error("internal syndrome mismatch");found=true;
            std::cout<<"{\"event\":\"witness\",\"weight\":"<<wt<<",\"support\":";print_support(selected,c.n);std::cout<<"}\n"<<std::flush;
        }return;}
        int budget=effective_W-wt;if(budget<=0||sw>budget*maxdeg)return;
        // Bucket the active checks by available degree, with no heap allocation
        // and no full scan of the check matrix at each search node.
        int ids[MAXM],next[MAXM],head[65],tail[65],count=0,best=-1,minavail=65;
        std::fill(head,head+65,-1);std::fill(tail,tail+65,-1);
        for(size_t k=0;k<syndrome.size();++k){uint64_t a=syndrome[k];while(a){int j=64*k+__builtin_ctzll(a);a&=a-1;
            int d=__builtin_popcountll(available[j]);if(!d)return;
            ids[count]=j;next[count]=-1;if(head[d]<0)head[d]=count;else next[tail[d]]=count;tail[d]=count;++count;
            if(d<minavail){minavail=d;best=j;}
        }}
        // These describe one valid inequality on this node's available sites.
        int completion_total = 0, completion_denominator = 0;
        // No packing can exceed the number of unsatisfied checks.
        if(sw>budget){
        if(++packing_epoch==0){std::fill(used_epoch.begin(),used_epoch.end(),0);packing_epoch=1;}int packing=0;
        for(int d=minavail;d<=maxrow;++d)for(int k=head[d];k>=0;k=next[k]){
            int j=ids[k];uint64_t a=available[j];bool intersects=false;
            while(a){int b=__builtin_ctzll(a);a&=a-1;int v=c.hr[j][b];if(used_epoch[v]==packing_epoch){intersects=true;break;}}
            if(!intersects){if(++packing>budget){++pack_prunes;return;}a=available[j];while(a){int b=__builtin_ctzll(a);a&=a-1;int v=c.hr[j][b];used_epoch[v]=packing_epoch;}}
        }
        // Fractional odd-check packing: integer row weights a_j have
        // sum_{j incident v} a_j <= D for EVERY currently available qubit.
        // Every odd check needs at least one added qubit, so any completion
        // has D*additional_weight >= sum_j a_j. No numerical LP is trusted.
        if(fractional_mode&&sw>budget){
            ++fractional_calls;
            if(++fractional_epoch==0){std::fill(fractional_mark.begin(),fractional_mark.end(),0);fractional_epoch=1;}
            if(fractional_proofs.is_open()||even_proofs.is_open())for(int i=0;i<count;++i)fractional_weights[ids[i]]=0;
            if(fractional_mode==-1){
                int maximum=0;
                for(int i=0;i<count;++i){uint64_t a=available[ids[i]];while(a){int b=__builtin_ctzll(a);a&=a-1;int v=c.hr[ids[i]][b];
                    if(fractional_mark[v]!=fractional_epoch){fractional_mark[v]=fractional_epoch;fractional_load[v]=0;}
                    maximum=std::max(maximum,int(++fractional_load[v]));}}
                completion_total = sw;
                completion_denominator = maximum;
                if(sw>maximum*budget){
                    ++fractional_prunes;
                    if(fractional_proofs.is_open()){for(int i=0;i<count;++i)fractional_weights[ids[i]]=1;fractional_certificate(wt,budget,count,ids,maximum);}
                    return;
                }
            }else{
                const int denominator=fractional_mode;int total=0;
                for(int pass=0;pass<denominator;++pass){
                    bool changed=false;
                    for(int d=minavail;d<=maxrow;++d)for(int k=head[d];k>=0;k=next[k]){
                        int j=ids[k];uint64_t a=available[j];bool fits=true;
                        while(a){int b=__builtin_ctzll(a);a&=a-1;int v=c.hr[j][b];
                            if(fractional_mark[v]==fractional_epoch&&fractional_load[v]>=denominator){fits=false;break;}}
                        if(!fits)continue;
                        changed=true;++total;if(fractional_proofs.is_open()||even_proofs.is_open())++fractional_weights[j];
                        if(total>denominator*budget){++fractional_prunes;fractional_certificate(wt,budget,count,ids,denominator);return;}
                        a=available[j];while(a){int b=__builtin_ctzll(a);a&=a-1;int v=c.hr[j][b];
                            if(fractional_mark[v]!=fractional_epoch){fractional_mark[v]=fractional_epoch;fractional_load[v]=0;}
                            ++fractional_load[v];}
                    }
                    if(!changed)break;
                }
                if(even_repair_cap&&even_bound(wt,budget,count,ids,next,head,minavail,denominator,total))return;
                completion_total = total;
                completion_denominator = denominator;
            }
        }
        if(sw>budget&&sw<=63&&packing+3>budget){
            uint64_t adj[63];for(int i=0;i<count;++i)index[ids[i]]=i;
            for(int i=0;i<count;++i){adj[i]=1ULL<<i;uint64_t a=available[ids[i]];
                while(a){int b=__builtin_ctzll(a);a&=a-1;for(int j:c.vc[c.hr[ids[i]][b]])if(unsatisfied(j))adj[i]|=1ULL<<index[j];}}
            int steps=0;if(independent((1ULL<<count)-1,budget+1,adj,steps)){++pack_prunes;return;}
        }
        } // optional work only; the pruning criterion is unchanged
        best=repair_check(best,wt,minavail,ids,next,head);
        struct Option { int v, score; bool impossible; };
        Option options[64];
        int size = 0;
        uint64_t a = available[best];
        while (a) {
            int bit_index = __builtin_ctzll(a);
            a &= a - 1;
            int v = c.hr[best][bit_index], score = 0;
            for (int check : c.vc[v]) score += unsatisfied(check);
            int load = fractional_mark[v] == fractional_epoch ? fractional_load[v] : 0;
            // Fixing x_v=1 in A <= sum c_q x_q leaves
            // A-c_v <= D*(budget-1). Retain the parent's verdict before
            // recursion changes the shared coefficient workspace.
            bool impossible = proposed_additions && completion_denominator > 0 &&
                completion_total - load > completion_denominator * (budget - 1);
            if (impossible) ++proposed_candidates;
            options[size++] = {v, score, impossible};
        }
        std::sort(options,options+size,[](Option a,Option b){return a.score!=b.score?a.score>b.score:a.v<b.v;});
        int blocked=0;
        for(int j=0;j<size;++j){if(wt==1&&j>=end)break;int v=options[j].v;block(v);++blocked;
            if(wt!=1||j>=begin){
                // Keep the usual sibling exclusion even when this child is skipped.
                if (options[j].impossible) {
                    ++proposed_prunes;
                    if (hashed && wt < split_weight) ++proposed_prefix_prunes;
                    continue;
                }
                flip(v,1);dfs(wt+1,hashed&&wt<split_weight?mix(key^uint64_t(v)):key);flip(v,-1);if(found||incomplete)break;}}
        for(int j=0;j<blocked;++j)unblock(options[j].v);
    }
    int run(){
        SymmetryRoots symmetry(c, P, symmetry_file);
        if (root >= int(symmetry.representatives.size()))
            throw std::runtime_error("root exceeds the number of symmetry orbits");
        start=std::chrono::steady_clock::now();
        int first=hashed?0:root,last=hashed?int(symmetry.representatives.size()):root+1;
        if(effective_W==0)roots_completed=last-first;
        else for(int r=first;r<last;++r){
            selected={};sw=bad=0;std::fill(forbidden.begin(),forbidden.end(),0);std::fill(syndrome.begin(),syndrome.end(),0);std::fill(overlap.begin(),overlap.end(),0);
            for(int j=0;j<c.m;++j){int d=c.hr[j].size();available[j]=d==64?~0ULL:((1ULL<<d)-1);}
            int v=symmetry.representatives[r];for(int j=0;j<=v;++j)block(j);flip(v,1);dfs(1,mix(uint64_t(r)));flip(v,-1);
            if(found||incomplete)break;++roots_completed;
        }
        std::cout<<"{\"event\":\"result\",\"status\":\""<<(found?"witness":incomplete?"incomplete":"excluded")
          <<"\",\"W\":"<<W<<",\"root\":"<<root<<",\"branch_begin\":"<<begin<<",\"branch_end\":"<<end
          <<",\"effective_W\":"<<effective_W<<",\"parity_cutoff_enabled\":"<<(use_parity?"true":"false")
          <<",\"kernel_even\":"<<(parity.even?"true":"false")<<",\"parity_trivial_exclusion\":"<<(effective_W==0?"true":"false")
          <<",\"parity_certificate_rows\":[";for(size_t i=0;i<parity.certificate_rows.size();++i){if(i)std::cout<<',';std::cout<<parity.certificate_rows[i];}std::cout<<']'
          <<",\"coset_pruning\":"<<(use_coset?"true":"false")<<",\"nodes\":"<<nodes<<",\"coset_prunes\":"<<coset_prunes
          <<",\"even_repair_cap\":"<<even_repair_cap<<",\"even_calls\":"<<even_calls<<",\"even_attempts\":"<<even_attempts<<",\"even_successes\":"<<even_successes<<",\"even_prunes\":"<<even_prunes
          <<",\"proposed_additions\":"<<(proposed_additions?"true":"false")
          <<",\"proposed_candidates\":"<<proposed_candidates
          <<",\"proposed_prunes\":"<<proposed_prunes
          <<",\"proposed_prefix_prunes\":"<<proposed_prefix_prunes
          <<",\"packing_prunes\":"<<pack_prunes<<",\"repair_depth\":"<<repair_depth<<",\"repair_calls\":"<<repair_calls<<",\"repair_changes\":"<<repair_changes<<",\"fractional_placement\":\"before_mis\",\"fractional_mode\":"<<fractional_mode<<",\"fractional_calls\":"<<fractional_calls<<",\"fractional_prunes\":"<<fractional_prunes<<",\"seconds\":"<<elapsed(start)
          <<",\"partition\":\""<<(hashed?"hash_prefix_v1":"root_branch_v1")<<"\",\"shard\":"<<shard<<",\"shards\":"<<shards<<",\"split_weight\":"<<split_weight
          <<",\"roots_completed\":"<<roots_completed<<",\"frontier_seen\":"<<frontier_seen<<",\"frontier_owned\":"<<frontier_owned
          <<",\"frontier_digest\":\""<<frontier_digest<<"\",\"common_nodes\":"<<common_nodes<<symmetry.metadata()<<"}\n"<<std::flush;
        return found?10:incomplete?75:0;
    }
};
int main(int argc,char **argv){try{
    if(argc<9){std::cerr<<"exact matrix P W seconds root branch_begin branch_end nodecap [no-coset]\n"
      <<"exact matrix P W seconds --shard id count split_weight nodecap [no-coset]\n";return 2;}
    std::signal(SIGTERM,stop_handler);std::signal(SIGINT,stop_handler);
    int p=std::stoi(argv[2]);if(p<1)throw std::runtime_error("invalid P");
    bool hashed=std::string(argv[5])=="--shard";
    if(hashed&&argc<10)throw std::runtime_error("missing shard parameters");
    bool proposed_additions = false;
    bool prune=true,parity_enabled=true;int repair_depth=0;int fractional_mode=0;int even_repair_cap=0;std::string fractional_file,even_file,symmetry_file;
    for(int i=hashed?10:9;i<argc;++i){
        std::string option=argv[i];
        if(option=="no-coset")prune=false;
        else if(option=="proposed-additions=on")proposed_additions=true;
        else if(option=="proposed-additions=off")proposed_additions=false;
        else if(option.rfind("symmetry-file=",0)==0) {
            symmetry_file=option.substr(14);
            if(symmetry_file.empty())throw std::runtime_error("empty symmetry file path");
        }
        else if(option.rfind("even-repairs=",0)==0){even_repair_cap=std::stoi(option.substr(13));if(even_repair_cap<0||even_repair_cap>8)throw std::runtime_error("invalid even repair cap");}
        else if(option.rfind("even-proofs=",0)==0)even_file=option.substr(12);
        else if(option=="fractional=off")fractional_mode=0;
        else if(option=="fractional=2")fractional_mode=2;
        else if(option=="fractional=4")fractional_mode=4;
        else if(option=="fractional=uniform")fractional_mode=-1;
        else if(option.rfind("fractional-proofs=",0)==0)fractional_file=option.substr(18);
        else if(option.rfind("repair-depth=",0)==0){repair_depth=std::stoi(option.substr(13));if(repair_depth<0||repair_depth>64)throw std::runtime_error("invalid repair depth");}
        else throw std::runtime_error("unknown option: "+option);
    }
    if(even_repair_cap&&fractional_mode<=0)throw std::runtime_error("even repairs require fractional=2 or4");
    Exact search(argv[1],p,std::stoi(argv[3]),std::stod(argv[4]),hashed?0:std::stoi(argv[5]),hashed?0:std::stoi(argv[6]),hashed?64:std::stoi(argv[7]),std::stoull(argv[hashed?9:8]),prune,parity_enabled);
    if(hashed){search.hashed=true;search.shard=std::stoi(argv[6]);search.shards=std::stoi(argv[7]);search.split_weight=std::stoi(argv[8]);
        if(search.shards<1||search.shard<0||search.shard>=search.shards||search.split_weight<1||search.split_weight>64)throw std::runtime_error("invalid shard partition");}
    search.proposed_additions = proposed_additions;
    search.symmetry_file=symmetry_file;
    search.fractional_mode=fractional_mode;search.repair_depth=repair_depth;search.even_repair_cap=even_repair_cap;
    if(!even_file.empty()){search.even_proofs.open(even_file);if(!search.even_proofs)throw std::runtime_error("cannot open even proof trace");}
    if(!fractional_file.empty()){search.fractional_proofs.open(fractional_file);if(!search.fractional_proofs)throw std::runtime_error("cannot open fractional proof trace");}
    return search.run();
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
