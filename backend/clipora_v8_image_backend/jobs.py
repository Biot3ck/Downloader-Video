"""Image requests are trusted-code only. No public submission or network client."""
import json
import re
from clipora_v8_web.platforms import recognize_media
from clipora_v8_web.owned_publish import PublicationDenied

FIXTURE='clipora:offline-images'


def create_fixture_job(store,token,key):
    if type(key) is not str or not re.fullmatch('[0-9a-f]{32}',key):raise ValueError('Invalid idempotency key')
    return store._submit(token,FIXTURE,key)


def create_image_job(store,token,url,key):
    if type(key) is not str or not re.fullmatch('[0-9a-f]{32}',key):raise ValueError('Invalid idempotency key')
    source=recognize_media(url,'images')
    payload=json.dumps({'version':1,'media_kind':'images','platform':source.platform,'url':source.url},sort_keys=True,separators=(',',':'))
    return store._submit(token,payload,key)


def image_payload(value):
    if value==FIXTURE:return True
    try:
        data=json.loads(value)
        if type(data) is not dict or set(data)!={'version','media_kind','platform','url'}:return False
        source=recognize_media(data['url'],'images')
        return (type(data['version']) is int and data['version']==1 and data['media_kind']=='images'
                and data['platform']==source.platform and data['url']==source.url
                and value==json.dumps(data,sort_keys=True,separators=(',',':')))
    except (ValueError,TypeError,UnicodeError):return False


def require_payload(store,job_id,owner):
    value=store.payload_for_runner(job_id,owner)
    if not image_payload(value):raise PublicationDenied('Image job fence rejected')
    return value
