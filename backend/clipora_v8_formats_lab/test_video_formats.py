"""Candidate policy tests; no network, platform access, worker, or HTTP unlock."""
import copy
import unittest
from clipora_v8_formats_lab.video_formats import choices,verify_output,MAX_BYTES


def source(identity,width=854,height=480,**extra):
    return dict(format_id=identity,width=width,height=height,vcodec='avc1.42',
                acodec='mp4a.40.2',ext='mp4',has_drm=False,filesize=10000,**extra)


def metadata(*formats):return {'duration':10,'formats':list(formats)}


def probe(plan):
    return {'format':{'format_name':'mov,mp4,m4a,3gp,3g2,mj2','duration':'10','size':'10000'},
            'streams':[{'codec_type':'video','codec_name':'h264','width':plan.width,'height':plan.height},
                       {'codec_type':'audio','codec_name':'aac'}]}


class VideoFormatTests(unittest.TestCase):
    def test_native_standard_hd_and_portrait(self):
        for width,height in ((1920,1080),(1080,1920)):
            result=choices(metadata(source('standard'),source('hd',width,height)))
            self.assertEqual(result['video'].format_ids,('standard',))
            self.assertEqual((result['hd'].width,result['hd'].height),(width,height))
            self.assertTrue(verify_output(result['hd'],probe(result['hd'])))

    def test_no_hd_from_standard_and_no_invented_low_resolution(self):
        self.assertNotIn('hd',choices(metadata(source('low'))))
        result=choices(metadata(source('high',1280,720)))
        self.assertNotIn('video',result)
        self.assertEqual(result['hd'].format_ids,('high',))

    def test_split_hd_requires_compatible_audio(self):
        video=source('video-only',1920,1080);video['acodec']='none'
        audio=source('audio-only');audio.update(vcodec='none',ext='m4a',width=0,height=0,abr=128)
        self.assertEqual(choices(metadata(video)),{})
        result=choices(metadata(video,audio))
        self.assertEqual(result['hd'].format_ids,('video-only','audio-only'))
        self.assertEqual(result['hd'].estimated_bytes,20000)
        self.assertEqual(result['mp3'].format_ids,('audio-only',))
        self.assertIsNone(result['mp3'].estimated_bytes)

    def test_unknown_or_unsafe_formats_cannot_be_offered(self):
        for key,value in [('height',None),('width',True),('has_drm',True),('has_drm',None),
                          ('vcodec','vp9'),('ext','webm'),('filesize',MAX_BYTES+1),('fps',float('nan'))]:
            with self.subTest(key=key,value=value):
                item=source('candidate',1280,720);item[key]=value
                self.assertNotIn('hd',choices(metadata(item)))

    def test_live_playlists_invalid_duration_and_ambiguous_ids_rejected(self):
        for key,value in [('is_live',True),('_type','playlist'),('has_drm',True),
                          ('duration',float('inf')),('duration',True),('duration',1801),('duration',10**1000)]:
            data=metadata(source('a'));data[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):choices(data)
        with self.assertRaises(ValueError):choices(metadata(source('a'),source('a',1280,720)))
        with self.assertRaises(ValueError):choices(metadata(*[source(str(i)) for i in range(257)]))

    def test_unknown_size_is_not_presented_as_exact_and_urls_never_escape(self):
        item=source('hd',1280,720);item.update(filesize=None,url='https://secret.invalid/token',http_headers={'Authorization':'private'})
        result=choices(metadata(item))
        self.assertIsNone(result['hd'].estimated_bytes)
        self.assertNotIn('secret',repr(result));self.assertNotIn('private',repr(result))

    def test_low_quality_wrong_codec_and_truncated_output_rejected(self):
        plan=choices(metadata(source('hd',1280,720)))['hd']
        for field,value in [('height',480),('width',True),('codec_name','vp9')]:
            data=probe(plan);data['streams'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):verify_output(plan,data)
        for field,value in [('duration','1'),('duration','nan'),('size',str(MAX_BYTES+1)),('size',10000.5),('format_name',None)]:
            data=probe(plan);data['format'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):verify_output(plan,data)

    def test_mp3_is_actual_audio_only_mp3_not_a_renamed_mp4(self):
        plan=choices(metadata(source('source')))['mp3']
        data={'format':{'format_name':'mp3','duration':'10.05','size':'10000'},
              'streams':[{'codec_type':'audio','codec_name':'mp3'}]}
        self.assertTrue(verify_output(plan,data))
        with self.assertRaises(ValueError):verify_output(plan,probe(plan))
        wrong=copy.deepcopy(data);wrong['streams'][0]['codec_name']='aac'
        with self.assertRaises(ValueError):verify_output(plan,wrong)


if __name__=='__main__':unittest.main()
