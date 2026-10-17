import os
from .archive import verify
from .formats import MAX_ALBUM
from .jobs import require_payload
from clipora_v8_web.owned_publish import publish_file,PublicationDenied


def publish_album(store,job_id,owner,source,directory):
    payload=require_payload(store,job_id,owner)
    def validate(fd):
        try:
            with os.fdopen(os.dup(fd),'rb') as stream:verify(stream)
        except Exception:raise PublicationDenied('Image album integrity rejected') from None
    return publish_file(store,job_id,owner,source,directory,suffix='.zip',minimum=64,maximum=MAX_ALBUM,
                        validate=validate,required_payload=payload)
