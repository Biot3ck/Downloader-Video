// Unit harness for request races and failure handling; no browser or network.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function setup(config=null){
  const elements=new Map(),listeners=new Map(),requests=[];
  function element(){
    const handlers={},attrs={};
    return {hidden:true,disabled:false,checked:false,value:'',textContent:'',dataset:{},
      classList:{toggle(){},add(){},remove(){}},addEventListener(name,fn){handlers[name]=fn;},
      setAttribute(name,value){attrs[name]=value;},removeAttribute(name){delete attrs[name];},
      replaceChildren(){},append(){},focus(){},attrs,
      emit(name){return handlers[name]?.({preventDefault(){}});}};
  }
  const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  get('format-video').value='video';get('format-hd').value='hd';get('format-mp3').value='mp3';
  const location={hash:'#video'};
  const clipboard={readText:async()=>''};
  const context=vm.createContext({document:{getElementById:get,querySelector:selector=>selector.includes('checked')?(['format-video','format-hd','format-mp3'].map(get).find(item=>item.checked)||get('format-video')):get('skip'),
      querySelectorAll:()=>[],createElement:element},
    navigator:{clipboard},
    window:{addEventListener:(name,fn)=>listeners.set(name,fn)},location,AbortController,setTimeout,clearTimeout,
    fetch:(url,options)=>url==='/api/v8/ui/config'
      ?Promise.resolve({ok:true,status:200,json:async()=>config||{real_downloads_enabled:false,demo_downloads_enabled:false}})
      :new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  vm.runInContext(fs.readFileSync(__dirname+'/assets/app.js','utf8'),context);
  return {get,requests,clipboard,submit:()=>get('downloadForm').emit('submit'),
    navigate(key){location.hash='#'+key;listeners.get('hashchange')();}};
}
const recognized={media_kind:'video',platform:'youtube',public_downloads_enabled:false,network_access_performed:false};
const respond=(request,data=recognized)=>request.resolve({ok:true,status:200,json:async()=>data});
const previewPayload={sample:true,platform:'youtube',media_kind:'video',title:'Sample clip · Youtube',
  caption:'Line one.\n\nLine two with #tags.',duration_seconds:3,width:640,height:360,
  preview_url:'/api/v8/demo/preview/token',poster_url:'/api/v8/demo/preview/poster',
  expires_in:300,network_access_performed:false};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

test('editing a checked URL clears its old recognition',async()=>{
  const ui=setup();ui.get('url').value='https://youtu.be/abc';
  const done=ui.submit();respond(ui.requests[0]);await done;
  assert.equal(ui.get('result').hidden,false);
  ui.get('url').value='https://pin.it/new';ui.get('url').emit('input');
  assert.equal(ui.get('result').hidden,true);
  assert.equal(ui.get('check-link').disabled,false);
});
test('editing during a request aborts it and ignores late completion',async()=>{
  const ui=setup(),old=ui.submit();
  ui.get('url').emit('input');
  assert.equal(ui.requests[0].options.signal.aborted,true);
  const current=ui.submit();
  respond(ui.requests[0]);await old;
  assert.equal(ui.get('check-link').disabled,true);
  assert.equal(ui.get('result-title').textContent,'Checking your link');
  respond(ui.requests[1]);await current;
  assert.equal(ui.get('check-link').disabled,false);
  assert.equal(ui.get('result-title').textContent,'YouTube link recognized');
});
test('changing downloader cannot display a late result in the new view',async()=>{
  const ui=setup(),done=ui.submit();ui.navigate('photo');
  respond(ui.requests[0]);await done;
  assert.equal(ui.get('result').hidden,true);
  assert.equal(ui.get('url-label').textContent,'Photo post URL');
  assert.equal(ui.get('downloadForm').attrs['aria-busy'],undefined);
});
test('HTML service errors and rate limits show plain, actionable messages',async()=>{
  for(const [status,expected] of [[503,'temporarily unavailable'],[429,'Too many checks']]){
    const ui=setup(),done=ui.submit();
    ui.requests[0].resolve({ok:false,status,json:async()=>{throw Error('private parser/server detail');}});
    await done;
    assert.ok(ui.get('result-description').textContent.includes(expected));
    assert.equal(ui.get('check-link').disabled,false);
  }
});
test('malformed JSON and unexpected success contracts never show success',async()=>{
  for(const data of [null,{...recognized,public_downloads_enabled:true},'invalid-json']){
    const ui=setup(),done=ui.submit();
    if(data==='invalid-json')ui.requests[0].resolve({ok:true,status:200,json:async()=>{throw SyntaxError('private response contents');}});
    else respond(ui.requests[0],data);
    await done;
    assert.equal(ui.get('result-title').textContent,'Could not check this link');
    assert.ok(!ui.get('result-description').textContent.includes('private'));
    assert.equal(ui.get('check-link').disabled,false);
  }
});
test('supported validation errors retain the actual API guidance',async()=>{
  const ui=setup(),done=ui.submit();
  ui.requests[0].resolve({ok:false,status:422,json:async()=>({detail:'Use a YouTube, TikTok, Instagram, or Pinterest post link.'})});
  await done;
  assert.equal(ui.get('result-description').textContent,'Use a YouTube, TikTok, Instagram, or Pinterest post link.');
});
test('format options appear only after a recognized link and never submit a download',async()=>{
  const ui=setup();
  assert.equal(ui.get('video-formats').hidden,true);
  const done=ui.submit();respond(ui.requests[0]);await done;
  assert.equal(ui.get('video-formats').hidden,false);
  assert.ok(ui.get('format-note').textContent.includes('not available'));
  for(const format of ['hd','mp3']){
    const before=ui.requests.length;
    ui.get('format-'+format).emit('change');
    assert.equal(ui.requests.length,before);
    assert.equal(ui.requests[0].url,'/api/v8/validate');
  }
  ui.navigate('photo');assert.equal(ui.get('video-formats').hidden,true);
  ui.navigate('video');assert.equal(ui.get('video-formats').hidden,true);
});
test('demo downloads only call the bundled sample endpoint',async()=>{
  const ui=setup();ui.get('url').value='https://youtu.be/abc';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
  assert.equal(ui.get('video-formats').hidden,false);
  assert.equal(ui.get('download-actions').hidden,false);
  assert.ok(ui.get('download-notice-text').textContent.includes('bundled sample'));
  assert.ok(ui.get('format-note').textContent.includes('Bundled sample'));
  assert.equal(ui.requests[1].url,'/api/v8/demo/preview');
  respond(ui.requests[1],previewPayload);await tick();
  const ready=ui.get('download-file').emit('click');
  assert.equal(ui.requests[2].url,'/api/v8/demo/download');
  assert.deepEqual(JSON.parse(ui.requests[2].options.body),{url:'https://youtu.be/abc',media_kind:'video',format:'video'});
  ui.requests[2].resolve({ok:true,status:200,json:async()=>({sample:true,format:'video',platform:'youtube',
    filename:'clipora-sample-youtube-video.mp4',url:'/api/v8/demo/file/token',network_access_performed:false})});
  await ready;
  assert.ok(ui.get('download-status').textContent.includes('clipora-sample-youtube-video.mp4'));
  assert.equal(ui.get('download-file').disabled,false);
});
test('a recognized demo link reveals a preview with the full caption before downloads',async()=>{
  const ui=setup();ui.get('url').value='https://youtu.be/abc';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
  assert.equal(ui.get('preview-card').hidden,false);
  assert.equal(ui.get('preview-placeholder').textContent,'Loading preview…');
  assert.equal(ui.requests[1].url,'/api/v8/demo/preview');
  assert.deepEqual(JSON.parse(ui.requests[1].options.body),{url:'https://youtu.be/abc',media_kind:'video'});
  respond(ui.requests[1],previewPayload);await tick();
  assert.equal(ui.get('preview-video').attrs.src,'/api/v8/demo/preview/token');
  assert.equal(ui.get('preview-video').attrs.poster,'/api/v8/demo/preview/poster');
  assert.equal(ui.get('preview-video').hidden,false);
  assert.equal(ui.get('preview-placeholder').hidden,true);
  assert.equal(ui.get('preview-caption').textContent,previewPayload.caption);
  assert.equal(ui.get('preview-title').textContent,'Sample clip · Youtube');
  assert.equal(ui.get('preview-platform').textContent,'YouTube');
  assert.equal(ui.get('preview-duration').textContent,'3s · 640×360');
  // Preview markup sits above the format picker and the download button.
  assert.equal(ui.get('video-formats').hidden,false);
  assert.equal(ui.get('download-actions').hidden,false);
});
test('photo previews use the bundled image and drop the poster',async()=>{
  const ui=setup();ui.navigate('photo');ui.get('url').value='https://pin.it/abc';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,media_kind:'images',platform:'pinterest',demo_downloads_enabled:true});await done;
  respond(ui.requests[1],{...previewPayload,media_kind:'images',platform:'pinterest',width:1280,height:720,
    duration_seconds:null,poster_url:null});await tick();
  assert.equal(ui.get('preview-image').attrs.src,'/api/v8/demo/preview/token');
  assert.equal(ui.get('preview-image').hidden,false);
  assert.equal(ui.get('preview-video').hidden,true);
  assert.equal(ui.get('preview-video').attrs.poster,undefined);
  assert.equal(ui.get('preview-duration').textContent,'1280×720');
  assert.equal(ui.get('format-note').textContent.startsWith('Bundled sample'),true);
});
test('preview failures and non-sample payloads never render media',async()=>{
  for(const payload of [{...previewPayload,preview_url:'https://evil.example/x'},
                        {...previewPayload,network_access_performed:true},
                        {...previewPayload,caption:null},
                        {...previewPayload,sample:false}]){
    const ui=setup();ui.get('url').value='https://youtu.be/abc';
    const done=ui.submit();
    respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
    respond(ui.requests[1],payload);await tick();
    assert.equal(ui.get('preview-video').hidden,true);
    assert.equal(ui.get('preview-placeholder').textContent,'Preview unavailable right now.');
  }
  const ui=setup();ui.get('url').value='https://youtu.be/abc';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
  ui.requests[1].resolve({ok:false,status:503,json:async()=>{throw Error('private');}});await tick();
  assert.equal(ui.get('preview-video').hidden,true);
  assert.equal(ui.get('preview-placeholder').textContent,'Preview unavailable right now.');
});
test('editing or switching views removes the old preview',async()=>{
  const ui=setup();ui.get('url').value='https://youtu.be/abc';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
  respond(ui.requests[1],previewPayload);await tick();
  assert.equal(ui.get('preview-card').hidden,false);
  ui.get('url').emit('input');
  assert.equal(ui.get('preview-card').hidden,true);
  assert.equal(ui.get('preview-video').attrs.src,undefined);
});
test('paste fills the URL field and checks the link automatically',async()=>{
  const ui=setup();
  ui.clipboard.readText=async()=>'  https://www.tiktok.com/@user/video/123  ';
  const done=ui.get('paste-link').emit('click');
  await tick();
  assert.equal(ui.get('url').value,'https://www.tiktok.com/@user/video/123');
  assert.equal(ui.requests[0].url,'/api/v8/validate');
  assert.deepEqual(JSON.parse(ui.requests[0].options.body),{url:'https://www.tiktok.com/@user/video/123',media_kind:'video'});
  respond(ui.requests[0]);await done;
  assert.equal(ui.get('result-title').textContent,'YouTube link recognized');
  assert.equal(ui.get('paste-link').disabled,false);
});
test('paste failures and empty clipboards explain what to do instead',async()=>{
  const ui=setup();
  ui.clipboard.readText=async()=>{throw Error('denied');};
  await ui.get('paste-link').emit('click');
  assert.equal(ui.get('result-title').textContent,'Could not read the clipboard');
  assert.equal(ui.requests.length,0);
  assert.equal(ui.get('paste-link').disabled,false);
  ui.clipboard.readText=async()=>'   ';
  await ui.get('paste-link').emit('click');
  assert.equal(ui.get('result-title').textContent,'Clipboard is empty');
  ui.clipboard.readText=async()=>'x'.repeat(2049);
  await ui.get('paste-link').emit('click');
  assert.equal(ui.get('result-title').textContent,'That link is too long');
  assert.equal(ui.requests.length,0);
});
test('the audio view reuses the video contract and downloads mp3',async()=>{
  const ui=setup();ui.navigate('audio');
  assert.equal(ui.get('url-label').textContent,'Video URL');
  assert.equal(ui.get('feature-label').textContent,'Audio Downloader');
  const done=ui.submit();
  assert.deepEqual(JSON.parse(ui.requests[0].options.body),{url:'',media_kind:'video'});
  respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
  // A fixed MP3 format means no picker and no photo-style image format.
  assert.equal(ui.get('video-formats').hidden,true);
  assert.equal(ui.get('download-button-label').textContent,'Download MP3');
  assert.deepEqual(JSON.parse(ui.requests[1].options.body),{url:'',media_kind:'audio'});
  respond(ui.requests[1],{...previewPayload,media_kind:'audio',duration_seconds:3,
    width:null,height:null,poster_url:null});await tick();
  assert.equal(ui.get('preview-audio').attrs.src,'/api/v8/demo/preview/token');
  assert.equal(ui.get('preview-audio').hidden,false);
  assert.equal(ui.get('preview-video').hidden,true);
  assert.equal(ui.get('preview-duration').textContent,'3s');
  const ready=ui.get('download-file').emit('click');
  assert.deepEqual(JSON.parse(ui.requests[2].options.body),{url:'',media_kind:'video',format:'mp3'});
  ui.requests[2].resolve({ok:true,status:200,json:async()=>({sample:true,format:'mp3',platform:'youtube',
    filename:'clipora-sample-youtube-mp3.mp3',url:'/api/v8/demo/file/token',network_access_performed:false})});
  await ready;
  assert.ok(ui.get('download-status').textContent.includes('clipora-sample-youtube-mp3.mp3'));
  // Leaving the view clears the audio preview source.
  ui.navigate('photo');
  assert.equal(ui.get('preview-audio').attrs.src,undefined);
});
test('a demo response that is not a bundled sample is rejected',async()=>{
  const ui=setup(),done=ui.submit();
  respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
  for(const payload of [{sample:true,url:'https://evil.example/x',network_access_performed:false},
                        {sample:false,url:'/api/v8/demo/file/token',network_access_performed:false},
                        {sample:true,url:'/api/v8/demo/file/token',network_access_performed:true}]){
    const ready=ui.get('download-file').emit('click');
    ui.requests.at(-1).resolve({ok:true,status:200,json:async()=>payload});
    await ready;
    assert.ok(!ui.get('download-status').textContent.includes('ready'));
  }
});
const realPreview={real:true,platform:'tiktok',media_kind:'video',title:'Real post',caption:'Real caption.',
  duration_seconds:12,width:1080,height:1920,preview_url:'/api/v8/real/media/token',
  poster_url:'/api/v8/real/media/poster',expires_in:900,network_access_performed:true};
test('a real link previews and downloads through the real endpoints',async()=>{
  const ui=setup();ui.get('url').value='https://www.tiktok.com/@tiktok/video/1';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,platform:'tiktok',real_downloads_enabled:true});await done;
  assert.equal(ui.get('video-formats').hidden,false);
  assert.equal(ui.get('download-actions').hidden,false);
  assert.equal(ui.get('format-note').textContent,'Real download: standard quality, up to 720p.');
  assert.ok(ui.get('download-notice-text').textContent.includes('Only download media you own'));
  assert.equal(ui.get('availability-text').textContent,'Live · real download');
  assert.equal(ui.requests[1].url,'/api/v8/real/preview');
  respond(ui.requests[1],realPreview);await tick();
  assert.equal(ui.get('preview-video').attrs.src,'/api/v8/real/media/token');
  assert.equal(ui.get('preview-video').attrs.poster,'/api/v8/real/media/poster');
  assert.equal(ui.get('preview-video').hidden,false);
  assert.equal(ui.get('preview-badge').textContent,'Live');
  assert.ok(ui.get('preview-note').textContent.includes('Fetched from TikTok just now'));
  assert.equal(ui.get('preview-caption').textContent,'Real caption.');
  assert.equal(ui.get('preview-duration').textContent,'12s · 1080×1920');
  const ready=ui.get('download-file').emit('click');
  assert.equal(ui.requests[2].url,'/api/v8/real/download');
  assert.deepEqual(JSON.parse(ui.requests[2].options.body),
    {url:'https://www.tiktok.com/@tiktok/video/1',media_kind:'video',format:'video'});
  ui.requests[2].resolve({ok:true,status:200,json:async()=>({real:true,format:'video',platform:'tiktok',
    filename:'clipora-tiktok-video.mp4',url:'/api/v8/real/file/token',network_access_performed:true})});
  await ready;
  assert.ok(ui.get('download-status').textContent.includes('clipora-tiktok-video.mp4'));
  assert.equal(ui.get('download-file').disabled,false);
});
test('real previews reject unsigned or non-live payloads',async()=>{
  for(const payload of [{...realPreview,real:false},{...realPreview,network_access_performed:false},
                        {...realPreview,preview_url:'https://evil.example/x'},
                        {...realPreview,preview_url:'/api/v8/demo/preview/token'},
                        {...realPreview,platform:'myspace'}]){
    const ui=setup();ui.get('url').value='https://www.tiktok.com/@tiktok/video/1';
    const done=ui.submit();
    respond(ui.requests[0],{...recognized,platform:'tiktok',real_downloads_enabled:true});await done;
    respond(ui.requests[1],payload);await tick();
    assert.equal(ui.get('preview-video').hidden,true);
    assert.equal(ui.get('preview-image').hidden,true);
    assert.equal(ui.get('preview-placeholder').textContent,'Preview unavailable right now.');
  }
});
test('real download errors keep the API guidance and never report success',async()=>{
  const ui=setup();ui.get('url').value='https://www.tiktok.com/@tiktok/video/1';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,platform:'tiktok',real_downloads_enabled:true});await done;
  respond(ui.requests[1],realPreview);await tick();
  const ready=ui.get('download-file').emit('click');
  ui.requests[2].resolve({ok:false,status:422,json:async()=>({detail:'This post contains photos only. Use the Photo Downloader.'})});
  await ready;
  assert.equal(ui.get('download-status').textContent,'This post contains photos only. Use the Photo Downloader.');
  assert.equal(ui.get('download-file').disabled,false);
  for(const payload of [{real:true,url:'https://evil.example/x',network_access_performed:true},
                        {real:false,url:'/api/v8/real/file/token',network_access_performed:true}]){
    const retry=ui.get('download-file').emit('click');
    ui.requests.at(-1).resolve({ok:true,status:200,json:async()=>payload});
    await retry;
    assert.ok(!ui.get('download-status').textContent.includes('ready'));
  }
});
test('real photo previews show image counts and bundle carousels',async()=>{
  const ui=setup();ui.navigate('photo');ui.get('url').value='https://www.tiktok.com/@a/photo/1';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,platform:'tiktok',media_kind:'images',real_downloads_enabled:true});await done;
  respond(ui.requests[1],{...realPreview,media_kind:'images',platform:'tiktok',image_count:3,
    duration_seconds:null,width:816,height:1452,poster_url:null});await tick();
  assert.equal(ui.get('preview-image').attrs.src,'/api/v8/real/media/token');
  assert.equal(ui.get('preview-image').hidden,false);
  assert.equal(ui.get('preview-image').alt,'Preview of the first image in this TikTok post');
  assert.equal(ui.get('preview-duration').textContent,'816×1452 · 3 images');
  assert.equal(ui.get('format-note').textContent,
    'Real download: original image files. Carousels are saved as a ZIP.');
  const ready=ui.get('download-file').emit('click');
  assert.deepEqual(JSON.parse(ui.requests[2].options.body),
    {url:'https://www.tiktok.com/@a/photo/1',media_kind:'images',format:'image'});
  ui.requests[2].resolve({ok:true,status:200,json:async()=>({real:true,format:'image',platform:'tiktok',
    filename:'clipora-tiktok-images.zip',url:'/api/v8/real/file/token',network_access_performed:true})});
  await ready;
  assert.ok(ui.get('download-status').textContent.includes('clipora-tiktok-images.zip'));
});

test('the availability line reflects the build mode before any check',async()=>{
  const real=setup({real_downloads_enabled:true,demo_downloads_enabled:false});
  await tick();
  assert.equal(real.get('availability-text').textContent,'Live · real download');
  assert.ok(real.get('download-notice-text').textContent.includes('Paste a link to preview'));
  const demo=setup({real_downloads_enabled:false,demo_downloads_enabled:true});
  await tick();
  assert.equal(demo.get('availability-text').textContent,'Demo · sample file');
  const closed=setup();
  await tick();
  assert.equal(closed.get('availability-text').textContent,'Downloads unavailable');
});
test('choosing MP3 relabels the download button and notes the format',async()=>{
  const ui=setup();ui.get('url').value='https://www.tiktok.com/@tiktok/video/1';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,platform:'tiktok',real_downloads_enabled:true});await done;
  assert.equal(ui.get('download-button-label').textContent,'Download video');
  ui.get('format-mp3').checked=true;ui.get('format-video').checked=false;ui.get('format-mp3').emit('change');
  assert.equal(ui.get('download-button-label').textContent,'Download MP3');
  assert.equal(ui.get('format-note').textContent,'Real download: MP3 audio at 192 kbps.');
  ui.get('format-hd').checked=true;ui.get('format-mp3').checked=false;ui.get('format-hd').emit('change');
  assert.equal(ui.get('download-button-label').textContent,'Download video');
  assert.equal(ui.get('format-note').textContent,'Real download: highest source quality, up to 1080p.');
});
test('real preview errors show the API guidance instead of a generic message',async()=>{
  const ui=setup();ui.get('url').value='https://www.instagram.com/p/abc/';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,platform:'instagram',real_downloads_enabled:true});await done;
  ui.requests[1].resolve({ok:false,status:422,
    json:async()=>({detail:'This post contains photos only. Use the Photo Downloader.'})});
  await tick();
  assert.equal(ui.get('preview-placeholder').textContent,
    'This post contains photos only. Use the Photo Downloader.');
  assert.equal(ui.get('preview-video').hidden,true);
  assert.equal(ui.get('download-actions').hidden,true);
  assert.equal(ui.get('video-formats').hidden,true);
});
test('a missing duration is filled in once the video loads',async()=>{
  const ui=setup();ui.get('url').value='https://www.instagram.com/reel/abc/';
  const done=ui.submit();
  respond(ui.requests[0],{...recognized,platform:'instagram',real_downloads_enabled:true});await done;
  respond(ui.requests[1],{...realPreview,platform:'instagram',duration_seconds:null,
    width:360,height:640});await tick();
  assert.equal(ui.get('preview-duration').textContent,'360×640');
  ui.get('preview-video').duration=12.4;
  ui.get('preview-video').emit('loadedmetadata');
  assert.equal(ui.get('preview-duration').textContent,'12s · 360×640');
  ui.get('preview-video').duration=99;
  ui.get('preview-video').emit('loadedmetadata');
  assert.equal(ui.get('preview-duration').textContent,'12s · 360×640');
});
