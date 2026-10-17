// Unit harness for request races and failure handling; no browser or network.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function setup(){
  const elements=new Map(),listeners=new Map(),requests=[];
  function element(){
    const handlers={},attrs={};
    return {hidden:true,disabled:false,value:'',textContent:'',dataset:{},
      classList:{toggle(){}},addEventListener(name,fn){handlers[name]=fn;},
      setAttribute(name,value){attrs[name]=value;},removeAttribute(name){delete attrs[name];},
      replaceChildren(){},append(){},focus(){},attrs,
      emit(name){return handlers[name]?.({preventDefault(){}});}};
  }
  const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
  const location={hash:'#video'};
  const context=vm.createContext({document:{getElementById:get,querySelector:()=>get('skip'),querySelectorAll:()=>[],createElement:element},
    window:{addEventListener:(name,fn)=>listeners.set(name,fn)},location,AbortController,setTimeout,clearTimeout,
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  vm.runInContext(fs.readFileSync(__dirname+'/assets/app.js','utf8'),context);
  return {get,requests,submit:()=>get('downloadForm').emit('submit'),
    navigate(key){location.hash='#'+key;listeners.get('hashchange')();}};
}
const recognized={media_kind:'video',platform:'youtube',public_downloads_enabled:false,network_access_performed:false};
const respond=(request,data=recognized)=>request.resolve({ok:true,status:200,json:async()=>data});

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
  const ui=setup(),done=ui.submit();
  respond(ui.requests[0],{...recognized,demo_downloads_enabled:true});await done;
  assert.equal(ui.get('video-formats').hidden,false);
  assert.equal(ui.get('download-actions').hidden,false);
  assert.ok(ui.get('download-notice-text').textContent.includes('bundled sample'));
  assert.ok(ui.get('format-note').textContent.includes('Bundled sample'));
  const ready=ui.get('download-file').emit('click');
  assert.equal(ui.requests[1].url,'/api/v8/demo/download');
  assert.deepEqual(JSON.parse(ui.requests[1].options.body),{url:'',media_kind:'video',format:'video'});
  ui.requests[1].resolve({ok:true,status:200,json:async()=>({sample:true,format:'video',platform:'youtube',
    filename:'clipora-sample-youtube-video.mp4',url:'/api/v8/demo/file/token',network_access_performed:false})});
  await ready;
  assert.ok(ui.get('download-status').textContent.includes('clipora-sample-youtube-video.mp4'));
  assert.equal(ui.get('download-file').disabled,false);
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
