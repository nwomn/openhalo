"""One backend request in flight; latest observation only; unverified caption cache."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    cache_s: float = 10.0
    cooldown_s: float = 2.0
    max_cooldown_s: float = 8.0
    max_result_age_s: float = 5.0
    observation_fresh_s: float = .65

class Scheduler:
    def __init__(self,config=Config()):
        self.config=config;self.key=None;self.payload=None;self.unknown=False
        self.seen=-1e9;self.pending=None;self.serial=0;self.cache=None
        self.retry_at=0;self.failures=0;self.events=[]

    def event(self,kind,t,**data):
        self.events.append(dict(type=kind,t=t,**data))

    def observe(self,t,key,payload=None,unknown=True):
        if key!=self.key:
            self.event('target_changed',t,old=self.key,new=key)
            self.cache=None;self.retry_at=0;self.failures=0
        self.key=key;self.payload=payload;self.unknown=unknown;self.seen=t

    def dispatch(self,t):
        if self.pending is not None:
            if self.key is not None and self.unknown:self.event('suppressed_pending',t,key=self.key)
            return None
        if self.key is None or not self.unknown or t-self.seen>self.config.observation_fresh_s:return None
        if self.cache is not None and t<self.cache['expires']:
            self.event('cache_reused',t,key=self.key);return None
        if t<self.retry_at:
            self.event('suppressed_cooldown',t,key=self.key);return None
        self.serial+=1
        self.pending=dict(id=self.serial,key=self.key,started=t,payload=self.payload)
        self.event('dispatched',t,id=self.serial,key=self.key)
        return self.pending.copy()

    def complete(self,request_id,t,text='',usable=True):
        if self.pending is None or self.pending['id']!=request_id:
            self.event('unmatched_completion',t,id=request_id);return False
        job=self.pending;self.pending=None
        stale=(job['key']!=self.key or self.key is None or
               t-self.seen>self.config.observation_fresh_s or
               t-job['started']>self.config.max_result_age_s)
        if stale:
            self.event('stale_discarded',t,id=request_id,job_key=job['key'],current_key=self.key);return False
        if not usable or not text.strip():
            self.failures+=1
            delay=min(self.config.max_cooldown_s,self.config.cooldown_s*2**min(self.failures-1,10))
            self.retry_at=t+delay
            self.event('cooldown_started',t,id=request_id,retry_at=self.retry_at);return False
        self.cache=dict(text=text,key=self.key,expires=t+self.config.cache_s,source_request=request_id,
                        status='unverified_model_caption')
        self.failures=0;self.retry_at=0
        self.event('caption_cached',t,id=request_id,key=self.key,expires=self.cache['expires'])
        return True
