#include "llama.h"
#include "mtmd.h"
#include "mtmd-helper.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <iostream>
#include <string>
#include <vector>
#include <chrono>
#include <sstream>

static void die(const char * s) { std::fprintf(stderr, "%s\n", s); std::exit(1); }
using clock_type = std::chrono::steady_clock;
static double elapsed_ms(clock_type::time_point t) { return std::chrono::duration<double,std::milli>(clock_type::now()-t).count(); }

static llama_context * make_ctx(llama_model * m, int batch, bool embeddings) {
    auto p = llama_context_default_params();
    p.n_ctx = std::max(128, batch); p.n_batch = p.n_ubatch = batch; p.embeddings = embeddings;
    auto * c = llama_init_from_model(m, p); if (!c) die("context init failed"); return c;
}

struct epfe_session {
    llama_context * ctx;
    llama_pos pos = 0;
    explicit epfe_session(llama_model * model, int max_batch) : ctx(make_ctx(model, max_batch, true)) {}
    ~epfe_session() { llama_free(ctx); }

    std::vector<float> push(const std::vector<float> & x, int n) {
        std::vector<float> y((size_t)n*2560);
        auto b=llama_batch_init(n,2560,1);b.n_tokens=n;
        for(int i=0;i<n;++i){std::copy_n(x.data()+(size_t)i*2560,2560,b.embd+(size_t)i*2560);b.pos[i]=pos+i;b.n_seq_id[i]=1;b.seq_id[i][0]=0;b.logits[i]=1;}
        if(llama_decode(ctx,b))die("EPFE decode failed");
        for(int i=0;i<n;++i)std::copy_n(llama_get_embeddings_ith(ctx,i),2560,y.data()+(size_t)i*2560);
        pos+=n;llama_batch_free(b);return y;
    }
};

static std::vector<float> run_classifier(llama_model * model, const std::vector<float> & x, int n) {
    auto p=llama_context_default_params();p.n_ctx=std::max(128,2*n);p.n_batch=p.n_ubatch=2*n;p.n_seq_max=n;
    auto *ctx=llama_init_from_model(model,p);if(!ctx)die("classifier context init failed");
    std::vector<llama_token>tok(2*n,0);std::vector<float>emb((size_t)2*n*2560,0);std::vector<llama_pos>pos(2*n);std::vector<int32_t>ns(2*n,1);std::vector<llama_seq_id>ids(2*n);std::vector<llama_seq_id*>seq(2*n);std::vector<int8_t>log(2*n,0);
    for(int i=0;i<n;++i){tok[2*i]=LLAMA_TOKEN_NULL;std::copy_n(x.data()+(size_t)i*2560,2560,emb.data()+(size_t)2*i*2560);pos[2*i]=0;pos[2*i+1]=1;ids[2*i]=ids[2*i+1]=i;seq[2*i]=&ids[2*i];seq[2*i+1]=&ids[2*i+1];log[2*i]=1;}
    llama_batch bat={2*n,tok.data(),emb.data(),pos.data(),ns.data(),seq.data(),log.data()};if(llama_decode(ctx,bat))die("classifier decode failed");
    std::vector<float>out((size_t)n*2);for(int i=0;i<n;++i)std::copy_n(llama_get_logits_ith(ctx,2*i),2,out.data()+2*i);llama_free(ctx);return out;
}

struct encoded_chunk { const mtmd_input_chunk * chunk; std::vector<float> embd; };

static std::string json_escape(const std::string & in) {
    std::string out; out.reserve(in.size()+8);
    for(char c:in){switch(c){case '\\':out+="\\\\";break;case '"':out+="\\\"";break;case '\n':out+="\\n";break;case '\r':out+="\\r";break;case '\t':out+="\\t";break;default:if((unsigned char)c>=32)out+=c;}}
    return out;
}

static std::string token_piece(const llama_vocab * vocab, llama_token tok) {
    char small[256]; int n=llama_token_to_piece(vocab,tok,small,sizeof(small),0,true);
    if(n>=0)return std::string(small,n);std::string out((size_t)-n,'\0');n=llama_token_to_piece(vocab,tok,out.data(),out.size(),0,true);out.resize(std::max(0,n));return out;
}

static std::string generate_shared(llama_model * base, mtmd_context * vision,
        const mtmd_input_chunks * chunks, const std::vector<encoded_chunk> & cache, int max_tokens) {
    auto cp=llama_context_default_params();
    int gen_ctx=16384, gen_batch=2048, gen_ubatch=512;
    if(const char*e=std::getenv("STREAMMIND_GEN_CTX"))gen_ctx=std::max(512,std::atoi(e));
    if(const char*e=std::getenv("STREAMMIND_GEN_BATCH"))gen_batch=std::max(128,std::atoi(e));
    if(const char*e=std::getenv("STREAMMIND_GEN_UBATCH"))gen_ubatch=std::max(64,std::atoi(e));
    cp.n_ctx=gen_ctx;cp.n_batch=gen_batch;cp.n_ubatch=gen_ubatch;
    std::unique_ptr<llama_context,decltype(&llama_free)> ctx(llama_init_from_model(base,cp),llama_free);if(!ctx)die("generation context init failed");
    llama_pos pos=0;size_t image_idx=0,n=mtmd_input_chunks_size(chunks);
    for(size_t i=0;i<n;++i){auto*c=mtmd_input_chunks_get(chunks,i);int r=0;if(mtmd_input_chunk_get_type(c)==MTMD_INPUT_CHUNK_TYPE_TEXT){r=mtmd_helper_eval_chunk_single(vision,ctx.get(),c,pos,0,2048,i+1==n,&pos);}else{if(image_idx>=cache.size())die("missing shared vision embedding");r=mtmd_helper_decode_image_chunk(vision,ctx.get(),c,const_cast<float*>(cache[image_idx++].embd.data()),pos,0,2048,&pos,nullptr,nullptr);}if(r)die("shared generation prefill failed");}
    std::unique_ptr<llama_sampler,decltype(&llama_sampler_free)> smpl(llama_sampler_init_greedy(),llama_sampler_free);const llama_vocab*vocab=llama_model_get_vocab(base);std::string text;
    for(int i=0;i<max_tokens;++i){llama_token tok=llama_sampler_sample(smpl.get(),ctx.get(),-1);llama_sampler_accept(smpl.get(),tok);if(llama_vocab_is_eog(vocab,tok))break;text+=token_piece(vocab,tok);llama_batch b=llama_batch_get_one(&tok,1);if(llama_decode(ctx.get(),b))die("shared generation decode failed");}
    return text;
}

int main(int argc,char**argv){
    if(argc<6){std::fprintf(stderr,"usage: %s backbone.gguf mmproj.gguf epfe.gguf classifier.gguf segment1.mcv [segment2.mcv ...]\n",argv[0]);return 2;}
    llama_backend_init();auto mp=llama_model_default_params();mp.n_gpu_layers=999;
    std::unique_ptr<llama_model,decltype(&llama_model_free)> base(llama_model_load_from_file(argv[1],mp),llama_model_free),epfe(llama_model_load_from_file(argv[3],mp),llama_model_free),cls(llama_model_load_from_file(argv[4],mp),llama_model_free);
    if(!base||!epfe||!cls)die("model load failed");auto vp=mtmd_context_params_default();vp.use_gpu=true;vp.print_timings=true;vp.n_threads=64;
    mtmd::context_ptr vision(mtmd_init_from_file(argv[2],base.get(),vp));if(!vision)die("mmproj load failed");
    int max_batch=1024;if(const char*e=std::getenv("STREAMMIND_BATCH"))max_batch=std::max(1,std::atoi(e));
    epfe_session epfe_state(epfe.get(),max_batch);int64_t timeline_offset=0;int segment_index=0;
    const char*prompt_env=std::getenv("STREAMMIND_PROMPT");std::string user_prompt=prompt_env?prompt_env:"";float threshold=.5f;if(const char*e=std::getenv("STREAMMIND_THRESHOLD"))threshold=std::atof(e);int max_tokens=128;if(const char*e=std::getenv("STREAMMIND_MAX_TOKENS"))max_tokens=std::max(1,std::atoi(e));int interval=0;if(const char*e=std::getenv("STREAMMIND_INTERVAL_SEGMENTS"))interval=std::max(0,std::atoi(e));int last_generated=-1000000;
    std::printf("{\"event\":\"ready\"}\n");std::fflush(stdout);
    auto process = [&](const std::string & input) {
      auto segment_started=clock_type::now();auto load_started=clock_type::now();
      auto media=mtmd_helper_bitmap_init_from_file(vision.get(),input.c_str(),false);if(!media.bitmap)die("MAGECV1 load failed");
      double container_ms=elapsed_ms(load_started);
      mtmd::input_chunks_ptr chunks(mtmd_input_chunks_init());std::string prompt="<|im_start|>user\n"+std::string(mtmd_get_marker(vision.get()))+"\n"+user_prompt+"<|im_end|>\n<|im_start|>assistant\n";mtmd_input_text text{prompt.data(),prompt.size(),false,true};const mtmd_bitmap* bm[]={media.bitmap};
      if(mtmd_tokenize(vision.get(),chunks.get(),&text,bm,1))die("media tokenize failed");
      std::map<int32_t,std::pair<std::vector<double>,size_t>> sums;std::map<int32_t,double> seconds;std::vector<const mtmd_input_chunk*> images;
      for(size_t i=0;i<mtmd_input_chunks_size(chunks.get());++i){auto*c=mtmd_input_chunks_get(chunks.get(),i);if(mtmd_input_chunk_get_type(c)==MTMD_INPUT_CHUNK_TYPE_IMAGE)images.push_back(c);}
      auto vision_started=clock_type::now();std::vector<encoded_chunk> encoded;int vision_encode_count=0;
      for(size_t first=0;first<images.size();){
        mtmd::batch_ptr batch(mtmd_batch_init(vision.get()));size_t last=first;
        for(;last<images.size();++last){int r=mtmd_batch_add_chunk(batch.get(),images[last]);if(r){if(last==first)die("cannot batch vision chunk");break;}}
        if(mtmd_batch_encode(batch.get()))die("Mage-ViT encode failed");++vision_encode_count;
        for(size_t i=first;i<last;++i){auto*c=images[i];size_t nt=mtmd_input_chunk_get_n_tokens(c);float*e=mtmd_batch_get_output_embd(batch.get(),c);encoded.push_back({c,std::vector<float>(e,e+nt*2560)});int32_t frame=-1;if(!mtmd_input_chunk_get_mage_timestamp_frame(c,&frame))continue;double sec=0;mtmd_input_chunk_get_mage_timestamp_seconds(c,&sec);seconds[frame]=sec;auto&v=sums[frame];if(v.first.empty())v.first.assign(2560,0);for(size_t t=0;t<nt;++t)for(int d=0;d<2560;++d)v.first[d]+=e[t*2560+d];v.second+=nt;}
        first=last;
      }
      double vision_ms=elapsed_ms(vision_started);
      if(sums.empty())die("no timestamped codec embeddings");std::vector<int32_t>frames;std::vector<float>means;for(auto&[f,v]:sums){frames.push_back(f);for(double z:v.first)means.push_back((float)(z/v.second));}
      auto epfe_started=clock_type::now();auto perception=epfe_state.push(means,(int)frames.size());double epfe_ms=elapsed_ms(epfe_started);
      auto classifier_started=clock_type::now();auto logits=run_classifier(cls.get(),perception,(int)frames.size());double classifier_ms=elapsed_ms(classifier_started);
      float peak=0;for(size_t i=0;i<frames.size();++i){float a=logits[2*i],b=logits[2*i+1],p=1.f/(1.f+std::exp(a-b));peak=std::max(peak,p);std::printf("{\"segment\":%d,\"source\":\"%s\",\"frame\":%d,\"seconds\":%.9g,\"timeline_index\":%lld,\"silent_logit\":%.7g,\"speak_logit\":%.7g,\"speak_probability\":%.7g,\"decision\":\"%s\"}\n",segment_index,input.c_str(),frames[i],seconds[frames[i]],(long long)(timeline_offset+i),a,b,p,p>=threshold?"speak":"silent");}
      bool triggered=!user_prompt.empty()&&(peak>=threshold||(interval>0&&segment_index-last_generated>=interval));double generation_ms=0;if(triggered){auto started=clock_type::now();std::string answer=generate_shared(base.get(),vision.get(),chunks.get(),encoded,max_tokens);generation_ms=elapsed_ms(started);last_generated=segment_index;std::printf("{\"event\":\"response\",\"segment\":%d,\"peak_probability\":%.7g,\"vision_encode_count\":%d,\"generation_ms\":%.3f,\"answer\":\"%s\"}\n",segment_index,peak,vision_encode_count,generation_ms,json_escape(answer).c_str());}else{std::printf("{\"event\":\"suppressed\",\"segment\":%d,\"peak_probability\":%.7g,\"vision_encode_count\":%d}\n",segment_index,peak,vision_encode_count);}
      timeline_offset+=frames.size();mtmd_bitmap_free(media.bitmap);std::fflush(stdout);
      std::fprintf(stderr,"STREAMMIND_TIMING {\"segment\":%d,\"timestamps\":%zu,\"container_ms\":%.3f,\"vision_ms\":%.3f,\"epfe_ms\":%.3f,\"classifier_ms\":%.3f,\"native_total_ms\":%.3f}\n",segment_index,frames.size(),container_ms,vision_ms,epfe_ms,classifier_ms,elapsed_ms(segment_started));
      ++segment_index;
    };
    if(argc==6 && std::string(argv[5])=="-"){
      std::string line;while(std::getline(std::cin,line)){if(!line.empty())process(line);}
    } else {
      for(int arg=5;arg<argc;++arg)process(argv[arg]);
    }
    llama_backend_free();
}
