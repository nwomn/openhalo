"""Frozen bounded claim checker. Retained image-only text is NOT validated truth."""
import re

VERSION='grounding-claims-v1'


def check(text, evidence, frame_id, pts, complete=True):
    aligned=evidence['frame_id']==frame_id and evidence['source_pts_seconds']==pts and evidence['pair_skew_ms']==0
    person=any(d['label']=='person' and d['confidence']>=0.5 for d in evidence['detections']) if aligned else False
    # Clause splitting is deliberately bounded; uncertain language is withheld,
    # never silently treated as supported. All original text is retained by caller.
    clauses=[c.strip(' .') for c in re.split(r'(?<=[.!?])\s+|\band\b|\bwhile\b',text) if c.strip(' .')]
    result=[]
    for clause in clauses:
        s=clause.lower()
        if not complete:
            status,reason='withdrawn','incomplete_response'
        elif not aligned:
            status,reason='withdrawn','frame_or_pts_mismatch'
        elif re.search(r'hold|holding|eat|drink|using|uses|typing|reading|watch|look.*(?:screen|monitor|computer|phone)|wave|waving|reach|pick|put|raise',s):
            status,reason='withdrawn','specific_relation_or_temporal_action_not_independently_measured'
        elif re.search(r'looking (?:at the camera|down)|head (?:down|lowered)|leaning|sitting|seated|standing|smil',s):
            status,reason='image_only_unverified','static_caption_retained_without_claiming_low_level_confirmation'
        elif re.fullmatch(r'(?:the |a )?(?:person|man|woman) (?:is )?(?:present|visible|in the image)',s) and person:
            status,reason='corroborated','same_frame_person_detection'
        else:
            status,reason='withdrawn','unparsed_or_unverified_specific_claim'
        result.append(dict(claim=clause,status=status,reason=reason))
    retained=[r for r in result if r['status']!='withdrawn']
    return dict(version=VERSION,aligned=aligned,claims=result,retained_claims=retained,
        withdrawn_claims=[r for r in result if r['status']=='withdrawn'],
        all_withdrawn=not retained,verified_claim_count=sum(r['status']=='corroborated' for r in result),
        boundary='image_only_unverified claims are captions, not verified state or Runtime observations')
